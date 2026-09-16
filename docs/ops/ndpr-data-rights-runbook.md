# ModishLog — NDPR Data Subject Rights Runbook (Interim, Manual Process)

## Why this exists

ModishLog collects personal data (name, email, phone) from every account
holder and records `ndpr_consent_given`/`ndpr_consent_at` at signup
(`backend/src/auth/models.py`, `schemas.py`) — but as of 2026-09-16 there is
no self-service way for a user to export their own data or request
erasure. Under NDPR (Nigeria Data Protection Regulation), data subjects
have both rights, and "we'll build it eventually" is not itself a
compliant answer to a request that arrives today.

**This is a template + interim stopgap, not the finished feature.** Given
the 2-day launch timeline, a full self-service export/erasure UI was
explicitly scoped out (task #220's own implementation notes) in favor of:
(1) this manual, support-handled process existing for real, right now, and
(2) a proper self-service feature built post-launch as its own task. The
`[ FILL IN ]` sections below are real operational decisions only the
founder can make — who owns these requests and what turnaround is
promised. Filling them in is the actual deliverable; this document alone
does not make ModishLog NDPR-compliant.

---

## Part 1 — Who handles these requests

| | |
|---|---|
| Data controller contact | Soji Soyoye — soji.soyoye@gmail.com |
| Who actions a request today | [ FILL IN — is it always the founder personally, or a named support inbox? ] |
| Turnaround commitment | [ FILL IN — e.g. "within 30 days of a verified request," the common NDPR-aligned baseline ] |
| How a user submits a request | [ FILL IN — support email address, or an in-app "Contact support" path — must be something the user can actually find, not just this internal doc ] |

---

## Part 2 — What personal data ModishLog actually holds

Two distinct categories — this runbook is about the first one.

### 2a. ModishLog account holders (the data subjects with NDPR rights against ModishLog)

| Table | PII fields | Notes |
|---|---|---|
| `businesses` | `name`, `phone`, `tax_number`, `country`, `state`, `city` | The business profile itself |
| `users` | `email`, `full_name`, `phone` (nullable) | Every staff account under a business |
| `audit_logs` | `actor_user_id` (FK to `users`) | References the account, not raw PII itself — see task #259 |

### 2b. The business's own end-customers (ModishLog is the processor, the business is the controller)

| Table | PII fields |
|---|---|
| `customers` | `name`, `contact_number`, `alternate_number`, `email`, `address`, `city`, `state`, `country`, `zip_code` |
| `sales` | `customer_name`, `contact_number` (free-text, not always linked to a `customers` row) |

A request about 2b (someone's own customer wants *their* data handled)
should be routed to the business owner, not actioned directly by ModishLog
support — ModishLog doesn't have standing to unilaterally act on another
business's customer records. This runbook covers 2a only.

---

## Part 3 — Fulfilling an access/export request (2a)

No self-service export endpoint exists yet. Manual process:

1. Verify the requester actually controls the account/email in question
   before acting (standard identity-verification step — don't skip this).
2. Connect to the production database (see
   [`docs/db-backup-recovery.md`](../db-backup-recovery.md) for connection
   details) and pull the requester's own rows:
   ```sql
   SELECT id, email, full_name, phone, role, is_active, created_at
   FROM users WHERE email = '<requester email>';

   SELECT id, name, phone, tax_number, country, state, city, created_at
   FROM businesses WHERE id = '<business_id from the users row above>';
   ```
3. Export the result as JSON or CSV and send it to the verified requester.
4. Record that the request was fulfilled: [ FILL IN — where should this be
   logged? A shared doc, an entry in `audit_logs` via a manual
   `record_audit_event` call, or something else — pick one and use it
   consistently, since there's currently no dedicated table for this ].

---

## Part 4 — Fulfilling an erasure request (2a)

**Important: an automatic erasure path already exists, but only at the
whole-business level.** Self-service business closure (task #252) starts a
30-day grace period (`BUSINESS_DELETION_GRACE_PERIOD_DAYS`), after which a
scheduled job (`purge-deleted-businesses.yml`, daily at 02:30 UTC) calls
`purge_expired_business_deletions()` → `_purge_business()`
(`backend/src/auth/service.py`), which anonymizes every user on that
business: `email` → `purged-<uuid>@deleted.modishlog.invalid`, `full_name`
→ `[deleted user]`, password rotated to a random unusable value, and the
business's own PII fields cleared.

**The gap**: this only fires when the *owner* closes the whole business.
An individual staff member (non-owner) asking for their personal data to
be erased while the business stays active has no matching path —
`deactivate_user()` only flips `is_active=False` and revokes sessions; it
does not touch `email`/`full_name`/`phone`.

Manual process until a real per-user erasure path exists:

1. Verify the requester (same as Part 3, step 1).
2. If the requester is the business **owner** and wants the whole account
   gone: point them at the existing self-service "Close business" flow in
   Settings — this already works end-to-end and needs no manual
   intervention.
3. If the requester is a **staff member** (not the owner) wanting only
   their own record erased: no self-service path exists yet. Manually run
   the same field-level anonymization `_purge_business()` applies, scoped
   to just that one user, via direct DB access — coordinate with
   [ FILL IN — who is authorized to run an ad-hoc production data
   mutation like this? Should probably require the same two-person
   awareness as anything else touching prod, per
   [`docs/ops/break-glass-runbook.md`](break-glass-runbook.md) ].
4. **Known, accepted gap** (already flagged in code comments, not new):
   neither path scrubs `sales.customer_name`/`sales.contact_number` —
   those are historical transaction records, not currently in scope for
   either erasure path. If a request specifically asks about this, it
   needs a real decision, not a silent skip — escalate rather than
   guessing.
5. Record that the request was fulfilled (same as Part 3, step 4).

---

## Part 5 — Post-launch: the real feature

This manual process is a stopgap, not the destination. Post-launch,
build:
- A genuine self-service data export endpoint (JSON/CSV dump of a user's
  own `users`/`businesses` rows, on request, no manual DB query needed).
- A genuine per-user erasure path (the same anonymization
  `_purge_business()` already does, but scoped to a single non-owner
  staff account, triggerable without direct DB access).
- A decision on the `sales.customer_name`/`contact_number` gap from Part
  4, step 4 — whether/how to handle it as part of either flow.

File this as its own task with proper TDD (per CLAUDE.md) rather than
folding it into this doc.

---

## Part 6 — Keeping this current

Re-read this end to end if `BUSINESS_DELETION_GRACE_PERIOD_DAYS` changes,
if `_purge_business()`'s field list changes, or if the support contact
changes. A stale version of Part 1 or Part 2 is worse than no doc at all —
it creates false confidence that a process exists when it's actually
pointing at a dead email address or an outdated table list.
