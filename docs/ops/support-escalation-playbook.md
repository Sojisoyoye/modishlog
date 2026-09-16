# ModishLog — Support & Escalation Playbook

## Why this exists

As of 2026-09-16, `contact@modishlog.com` was already the app's configured
reply-to address for transactional emails (verification, password reset —
see `EMAILS_FROM_EMAIL` in `backend/src/core/config.py`), but nothing
surfaced it to a logged-in user, and there was no written plan for who
actually handles an incoming message or a production outage. Launching to
real SMB owners without a working "how do I reach you" path, or a
"who does what" plan for when something breaks, is a real operational gap
task #235 exists to close.

**This is a template + interim playbook, not a fully staffed support
operation.** The `[ FILL IN ]` sections are real operational decisions —
who actually monitors the inbox, on what cadence, who's on point for an
outage — that only the founder can make. A full chat widget
(Crisp/Intercom/etc.) can follow post-launch; a monitored inbox + this
playbook is the minimum that must exist before real users start hitting
issues.

---

## Part 1 — How a user reaches you

| | |
|---|---|
| Support address | `contact@modishlog.com` (mailto link in the app sidebar, every logged-in page) |
| Who monitors it | [ FILL IN — is this an inbox the founder checks directly, or forwarded/shared with someone else? ] |
| Checked how often | [ FILL IN — e.g. "checked at least once per business day" ] |
| First-response target | [ FILL IN — e.g. "within 24 hours" — pick something realistic for a solo/small team at launch, not aspirational ] |

---

## Part 2 — Day-one triage: where to look first

When a report comes in (via `contact@modishlog.com` or otherwise), before
doing anything else:

1. **Is the whole app down?** Check
   `https://api.modishlog.com/health/deep` directly. It distinguishes a
   real outage from a degraded-but-serving state:
   - `"status": "unhealthy"` (503) — the database itself is unreachable.
     This is the one that actually blocks users from doing anything.
   - `"status": "degraded"` (200) — a non-critical dependency (FX API,
     Anthropic, Redis, or email/Resend — see task #263) is down, but the
     core app still works. Lower urgency, but still worth checking the
     `checks` object to see which one and whether it's expected (e.g. a
     deliberately unconfigured key vs. a real failure).
2. **Is it isolated to one user/business?** Cross-check whether the
   report matches a known single-tenant issue (bad input data, a
   business-specific edge case) vs. something systemic. `is_active`,
   role, and recent actions for the affected account are visible via the
   admin `/settings/users` page if you have access to that business, or
   directly in the audit log (`GET /api/v1/audit-log`, task #246/#259 —
   surfaces actor name/email now, not just a raw UUID) for anything
   sensitive that happened on their account.
3. **Check Sentry** for any exception around the reported time —
   [ FILL IN — Sentry project URL/org, if not already obvious from
   `SENTRY_DSN` in the deployed environment ]. `SENTRY_DSN` is already
   wired into both frontend and backend error handling; PII scrubbing is
   applied before events are sent (task R6, `test_reliability_fixes.py`),
   so a Sentry event is safe to open without extra caution there.
4. **Check backend logs directly** if Sentry doesn't have it (e.g. a
   structlog `warn`/`info` event, not an exception): SSH to production
   (see [`break-glass-runbook.md`](break-glass-runbook.md) for access) and
   `docker compose logs backend --tail 200` — every request and most
   significant domain events (logins, audit-logged actions, rate-limit
   hits) are structured JSON log lines there.

---

## Part 3 — Who's on point for a production outage

| Scenario | Who | Notes |
|---|---|---|
| Any production outage | [ FILL IN — presumably the founder solo at launch; name a second contact if one exists, matching break-glass-runbook.md's Part 1 ] | |
| Escalation path if the primary is unreachable | See [`break-glass-runbook.md`](break-glass-runbook.md) | Same underlying access-continuity problem — don't duplicate that doc's content here, just point to it |

For the actual mechanics of rolling back a bad deploy, rotating a leaked
secret, or fixing a DNS issue, `break-glass-runbook.md`'s Part 3 already
has concrete, verified steps — this playbook is about *triage and who
gets notified*, that one is about *what to actually do once you're in*.

---

## Part 4 — Keeping this current

Re-read this end to end if the support address changes, if who monitors
it changes, or if a new health-check dependency is added to
`/health/deep` (Part 2 above should stay in sync with what that endpoint
actually reports).
