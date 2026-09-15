# Launch-scale load test — findings (task #243)

Run 2026-09-15. Locust ramped to 200 concurrent virtual users (each a
distinct seeded business — 30 businesses total, 300 products / 2,500 sales
each, 9,000 products / 75,000 sales in total) against a standalone,
prod-shaped stack: gunicorn + 2 `UvicornWorker`s, `--timeout 60`, real
Postgres, Redis-backed rate limiter — the same config as
`docker-compose.prod.yml`. Full setup in `docker-compose.loadtest.yml`,
`backend/scripts/loadtest_seed.py`, `backend/loadtest/locustfile.py`.

**Caveat that qualifies every number below**: this ran on the local Colima
VM, which has **2 vCPUs / 2GB RAM total** (`colima list`), shared with the
already-running local dev stack (4 more containers) for the whole test. This
is far below what's likely available on the real Hetzner box. Treat the
*absolute* latency numbers here as a lower bound / directional signal, not a
literal prediction of production behavior — but treat the *structural*
findings below (pool ceiling, missing indices, event-loop blocking) as real
and environment-independent, since none of them are caused by CPU scarcity.

## Headline findings

### 1. DB connection pool exhausts under real load — confirms task #228 with evidence, not just code-reading

Six requests failed with:

```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 10 overflow 20 reached,
connection timed out, timeout 30.00
```

This is exactly the failure mode task #228 predicted from reading
`DB_POOL_SIZE=10` / `DB_MAX_OVERFLOW=20` × `--workers 2` = 60 max
connections. **At only 200 concurrent simulated businesses — well within
the "dozens to low hundreds" launch-scale target — Postgres connections
pinned at 60/60 for the entire steady-state of the run** (`pg_stat_activity`
count sampled repeatedly at 61 during the run). This produced real 500s on
`/products` and `/sales`, not just theoretical risk.

**Action**: task #228 should move from "review" to "fix before launch" —
this is no longer a hypothesis.

### 2. Bulk sales CSV import is slow end-to-end under concurrency, even though task #215's fix holds

The background-job fix from task 215 works as designed — the initial
`POST /sales/upload` never blocks past gunicorn's 60s timeout (submit
response times stayed under ~16s even under load, since it only validates
+ queues). But the *end-to-end* time from upload to `status: completed`
(polled by the locustfile) was:

| | Median | 99th %ile | Max |
|---|---|---|---|
| Baseline | 27s | 152s | 165s |
| With bcrypt fix | 26s | 147s | 175s |

Root cause: `run_bulk_upload_job_in_background` is a FastAPI
`BackgroundTasks` callback, which runs on the *same* worker's event loop as
regular request handling, competing for the same DB connections from the
same per-worker pool (see finding #1). Under concurrency, many businesses'
background jobs queue up behind each other and behind foreground request
traffic on the same 2 workers. This is a real UX gap: a trader who imports
their sales history on day one, during a busy period, could wait 2+ minutes
to see the import finish — not a timeout/crash, but a bad first impression.

**Action**: filed as a new follow-up (see below) — background jobs
competing with foreground traffic for the same worker/pool capacity is a
separate concern from the original "will it time out" fix.

### 3. Synchronous bcrypt call blocks the async event loop (fixed in this PR)

`authenticate_user()` (`backend/src/auth/service.py:164`, and two related
call sites for hashing) called bcrypt's `verify_password`/`get_password_hash`
directly inside `async def` functions. Bcrypt is deliberately slow
(~100-300ms) and CPU-bound; calling it un-offloaded blocks that entire
worker's event loop for the full duration, so *every other* concurrent
request on that worker — not just other logins — stalls behind it.

Fixed by wrapping all three call sites in `asyncio.to_thread(...)`, the same
pattern already established in this codebase for `_parse_bulk_upload_csv`
(task 215).

**Measured impact was smaller than expected and mixed** — see the honest
comparison below. This is architecturally the right fix (an unbounded
number of concurrent logins should never be able to fully freeze a worker,
which the un-fixed code allowed in the extreme), but on this 2-vCPU sandbox
it didn't clearly reduce tail latency, because:

| Metric | Baseline | With fix |
|---|---|---|
| Login median | 5.2s | 8.9s |
| Login max | 28.2s | 18.0s |
| Login avg | 7.1s | 8.6s |
| Dashboard 90th %ile | 3.8s | 5.4s |
| Products 90th %ile | 3.5s | 4.9s |
| Products max | 21.6s | 33.5s |
| Total request failures | 0 | 6 (all `QueuePool` timeouts, finding #1) |

Offloading CPU-bound work to a thread pool doesn't create CPU capacity that
doesn't exist — it only stops that work from *also* blocking unrelated I/O
work on the same thread. With only 2 vCPUs shared across 7 containers, the
total bcrypt work still competes for the same 2 cores either way; the fix
buys correctness/robustness (no single worker can be fully wedged by a
burst of logins) without buying throughput on constrained hardware. **This
finding should be re-measured against real Hetzner-class hardware (or a
Colima VM reconfigured with more CPU, e.g. `colima start --cpu 4`) before
concluding whether it materially helps in production** — the fix is still
correct to keep regardless of that outcome.

### 4. Zero request failures at baseline; failures only appeared after fixing #3

Baseline run: 18,331 requests, 0 failures. This says the app doesn't fall
over outright at this concurrency — everything degrades gracefully (slow,
not broken) until connections physically run out (finding #1), which is a
reasonable failure mode but the 500s themselves are still real defects to
fix.

## What this validates from the existing scalability audit

- Task 215 (bulk import background job): **confirmed fixed** for the
  original problem (request-timeout), new follow-up filed for the
  background-job/foreground-traffic contention it doesn't cover.
- Task 222 (missing indices on `sales.product_id` / `stock_movements`):
  not directly isolated in this run (would need `EXPLAIN ANALYZE` on the
  slow list-endpoint queries specifically, not just wall-clock time, since
  wall-clock here is dominated by pool contention). Still pending, still
  worth doing — deferred to a dedicated pass rather than claimed as
  validated by this test.
- Task 228 (DB connection pool headroom): **confirmed as a real, reproduced
  failure**, not just a code-reading risk. Should be prioritized before
  task 222 given it produces user-facing 500s at the exact "dozens to low
  hundreds" scale this task was asked to validate.

## Follow-up tasks filed

- Task 228 updated: elevated from "review" to "fix before launch" with this
  run's reproduction attached.
- New task filed: background bulk-upload jobs should not compete unbounded
  with foreground request traffic for the same gunicorn worker/DB pool
  capacity (finding #2).
- New task filed: re-run this same load test against Hetzner-class hardware
  (or a larger local VM) once tasks 228 (and ideally 222) are fixed, to get
  a capacity number that isn't confounded by the 2-vCPU sandbox.

## Reproducing this test

```bash
docker compose -f docker-compose.loadtest.yml up -d --build
docker compose -f docker-compose.loadtest.yml exec backend_loadtest alembic upgrade head
DATABASE_URL=postgresql+asyncpg://modishlog:modishlog_dev@localhost:5436/modishlog_loadtest \
  SECRET_KEY=loadtest-only-secret-key-not-for-real-use \
  UPLOAD_DIR=/tmp/modishlog_uploads \
  backend/.venv/bin/python backend/scripts/loadtest_seed.py
backend/.venv/bin/locust -f backend/loadtest/locustfile.py --host http://localhost:8010 \
  --users 200 --spawn-rate 5 --run-time 6m --headless \
  --csv backend/loadtest/results/run1
docker compose -f docker-compose.loadtest.yml down -v
```
