# Subscription & Billing Model — Spec

Status: decided (task #237), ready for implementation tasks to build against.
Decisions below were made directly by the business owner on 2026-09-15; this
doc is the reference for every downstream billing task (schema, gateway
integration, webhooks, paywall, frontend).

## 1. Gateway

**Paystack.** Reasons: strongest NGN card/bank/transfer coverage, native
recurring-billing primitives (Plans + Subscriptions API), hosted checkout
(Paystack Inline / Standard Checkout) so raw card data never touches
ModishLog's servers. Matches the app's existing NGN-first assumptions
(cashflow/pricing already CBN-sourced).

Do not build a custom card-entry form. All charge collection goes through
Paystack's hosted checkout/tokenization.

## 2. Pricing tiers

Two tiers, feature-gated:

| Tier  | Price (indicative — final number TBD by business) | Includes |
|-------|----|----------|
| Basic | Lower monthly price | Core sales, inventory, purchase orders/suppliers, customers, expenses, dashboard, reports, stock counts. Single user per business. |
| Pro   | Higher monthly price | Everything in Basic, plus: AI pricing/reorder suggestions (`ai_engine` domain), demand forecasting, multi-currency/FX tools (`fx`, cashflow FX bridge), multi-user access per business (additional team members beyond the owner), invoice schemes / custom invoicing. |

Gating boundary is the existing `ai_engine` and `fx` domains plus multi-user —
these are the features that don't exist yet for free/Basic users today, so
gating them doesn't remove anything currently-shipped from any existing
business (per the backup drill: 2 businesses, 2 users total, pre-launch).

Exact tier pricing (naira amounts) is a business decision to make at
launch-pricing time, not part of this spec — this doc fixes the *shape*
(2 tiers, what's gated) so schema/webhook work can start.

## 3. Billing cycle & trial

- **Monthly billing only** at launch. No annual option yet (avoids
  proration/plan-migration complexity pre-launch; can add later without
  breaking the schema below — annual would just be another Paystack Plan
  code per tier).
- **7-day free trial**, no card required to start the trial. Card is
  collected (via Paystack hosted checkout) only when the trial converts to
  a paid subscription or the user upgrades early.
- Trial start = business creation (`Business.created_at`, already exists).
  No separate trial-tracking table needed — trial end is a derived field
  (`created_at + 7 days`), not stored state.

## 4. Grace period & lapse behavior

- On a failed recurring charge, Paystack fires a webhook
  (`subscription.not_renew` / `invoice.payment_failed` depending on event
  type used). ModishLog moves the business into `past_due`.
- **3-day grace period** from the first failed charge: business keeps full
  read-write access. Paystack's own retry schedule (it retries failed
  charges automatically) runs concurrently — a successful retry within the
  window clears `past_due` back to `active`.
- After 3 days still unresolved: business moves to **read-only mode** — no
  writes to sales/inventory/orders/expenses/etc., but all existing data
  remains visible and exportable. Login still works (needed so the owner can
  see the paywall and re-subscribe). This is enforced centrally, not
  per-router (see §6).
- No hard lockout, no data deletion, at any point. Resubscribing (successful
  charge) immediately restores read-write access.

## 5. Currency

- **NGN primary.** All Paystack plans are NGN-denominated; this is the
  default and only option shown to Nigerian card/bank customers.
- **USD as a secondary display/charge option** for businesses that select USD
  as their operating currency (existing `Business.currency` field already
  supports non-NGN — see `fx` domain). Paystack supports USD subscriptions
  for supported card types; if a business's `Business.currency == "USD"`,
  create/charge against the USD-denominated Plan instead of the NGN one.
  Two Paystack Plan codes per tier (NGN + USD), not runtime FX conversion of
  a single price — avoids exchange-rate drift inside billing itself, which
  must never float against real invoiced amounts.

## 6. Schema/enforcement sketch (for the implementation task, not built here)

- New fields on `Business`: `subscription_status` (enum: `trialing`,
  `active`, `past_due`, `read_only`, `canceled`), `subscription_tier` (enum:
  `basic`, `pro`), `trial_ends_at` (derived, or stored if trial-extension
  logic is ever needed), `paystack_customer_code`,
  `paystack_subscription_code`, `current_period_end`.
- Enforcement is a single dependency/middleware checked on every
  state-changing request (POST/PUT/PATCH/DELETE) per the multi-tenant
  `business_id` isolation pattern already used for row-level scoping — reuse
  that seam rather than adding gating in every router individually.
- Webhook endpoint verifies Paystack's signature header before trusting any
  event payload (never trust an unverified webhook body for a real money
  system).

## 7. Explicitly out of scope for this spec / launch v1

- Annual billing, proration, mid-cycle upgrades/downgrades between tiers.
- Usage-based add-ons or metered billing.
- Refund/dispute tooling beyond whatever Paystack's dashboard provides
  out of the box.
- A dedicated `subscriptions` table history — v1 tracks current state only
  on `Business`; historical billing events live in Paystack's own dashboard.
