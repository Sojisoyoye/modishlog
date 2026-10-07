# Bulk-upload concurrency re-test — findings (ad-hoc, no task number yet)

Run 2026-10-07. Same standalone stack, same seed data, same Locust parameters
as tasks #243/#256 (`--users 200 --spawn-rate 5 --run-time 6m`, 30 seeded
businesses / 9,000 products / 75,000 sales), local Colima at 2 vCPU / 4GB
(not reconfigured to 4 vCPU this time — this investigation wasn't CPU-bound,
see below).

**Why this ran**: task #256 (2026-09-16) found `BULK_UPLOAD_MAX_CONCURRENT_JOBS
= 2` (task #255) caused 98.6% of bulk-upload jobs to fail/time out under
realistic concurrency, and explicitly flagged it as needing a fix -- but no
follow-up task was ever filed, so it sat unfixed for three weeks until this
session re-surfaced it while discussing concurrency/load-testing generally.

## What was tested

Three values for `BULK_UPLOAD_MAX_CONCURRENT_JOBS`, each a fresh `down -v` +
re-seed to avoid cross-run contamination (the first attempt below was run
without a clean teardown and produced misleading orphaned-job data — don't
reuse a loadtest DB volume across config changes):

| Cap (per worker, 2 workers) | Collateral damage to OTHER endpoints | Bulk-upload JOB completions |
|---|---|---|
| 8 (16 system-wide) | **Bad** -- `QueuePool limit...reached` reappears (task #228's bug), sustained across ~3 of the 6-minute run, spreading 500s to `/products`, `/sales`, `/dashboard`, `/reports`, not just uploads | 2/2 succeeded (158s each) |
| 4 (8 system-wide) | Contained to the pre-existing login-burst window only (see below) -- no sustained spread to other endpoints | 0/9 succeeded within the 60-poll (~60s) budget; DB check afterward: 1 FAILED, 8 PROCESSING, 42 PENDING, 4 PARTIAL (avg 163s), 0 COMPLETED |

**Decision: keep 4.** It measurably removes the dangerous cross-endpoint
cascade that 8 reintroduced, without making the bulk-upload-specific
situation meaningfully worse than any other value would -- see root cause
below, which no concurrency-slot count fixes.

## Root cause of bulk-upload jobs timing out (not a concurrency problem)

Jobs that DID reach a terminal status took 146-167 seconds for a 500-row
CSV, regardless of whether they had to wait for a semaphore slot. That
single number already exceeds the Locust poll budget (60 attempts, ~1s
apart) on its own. Traced to `_process_bulk_upload_rows()`
(`backend/src/sales/service.py:694`): it calls the full `create_sale()`
business-logic path (stock validation, inventory level update, stock
movement insert, sale insert) once per row, serially, in a plain `for`
loop -- a 500-row file is 500 sequential round trips of real work, not a
batch operation. This is the same pattern already flagged (and never
fixed) as finding #4 in the 2026-09-10 pre-launch audit
(`project_session_sep10_2026_launch_audit` memory): "Bulk sales CSV upload
... do one DB round-trip storm per row, synchronously."

**Raising/lowering `BULK_UPLOAD_MAX_CONCURRENT_JOBS` cannot fix this** --
it only changes how many slow jobs run in parallel, not how slow each one
is. A real fix needs batching the row-processing logic itself (e.g. bulk
stock/inventory updates per product rather than per row, a single
executemany-style insert for the Sale rows) -- a materially bigger change
than this config tune, touching `create_sale()`'s call path used
elsewhere too. Not attempted in this session.

## Login-burst failures (pre-existing, not caused by this investigation)

Every run (cap=8, cap=4 contaminated, cap=4 clean) showed a cluster of
`POST /auth/login` 500s (`QueuePool limit...reached`) confined to an
8-90 second window right at the start of the run, when Locust's spawn
ramp fires ~200 near-simultaneous logins. This matches task #256's own
finding that bcrypt verification is CPU-bound and only meaningfully
improves with more real CPU cores (confirmed 6-9x faster going 2->4
vCPU) -- not something this session's change affects either way. Real
Hetzner hardware's actual vCPU count was never confirmed against this
local Colima approximation; worth checking before assuming this
resolves itself in production.

## Follow-up (not done this session)

- File a real task for the `_process_bulk_upload_rows` per-row round-trip
  fix -- this is the actual blocker for "many businesses importing their
  sales history on day one," which is a real onboarding path per the
  Sep 10 audit, not a hypothetical.
- Confirm the real Hetzner box's vCPU count against the login-burst
  finding above.

## Reproducing this test

Same as `.taskmaster/docs/loadtest-findings-243.md`'s reproduction steps
(no Colima reconfiguration needed -- this investigation isn't CPU-bound).
Always `docker compose -f docker-compose.loadtest.yml down -v` between
runs that change backend config -- reusing a volume across config
changes contaminates job-table state with jobs orphaned by the container
restart, as happened on this session's first (discarded) cap=4 attempt.
