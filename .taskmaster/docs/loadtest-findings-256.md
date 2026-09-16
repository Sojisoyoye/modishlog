# Load test re-run on a larger local VM — findings (task #256)

Run 2026-09-16. Same standalone stack, same seed data, same Locust
parameters as task #243's original run (`--users 200 --spawn-rate 5
--run-time 6m`), but with the local Colima VM reconfigured from **2 vCPUs
/ 2GB RAM** to **4 vCPUs / 4GB RAM** (`colima stop && colima start --cpu 4
--memory 4`), approximating real Hetzner-class headroom rather than a
sandbox shared with the whole dev stack. A real Hetzner box was not
provisioned for this run (would require new cloud credentials/spend not
available here) — this is the "cheaper first approximation" the task
itself names as an acceptable substitute.

Results: `backend/loadtest/results/run3_4cpu_stats.csv` (compare against
`baseline_stats.csv` and `run2_stats.csv` from task #243).

## Headline finding 1 (good news): the bcrypt `asyncio.to_thread` fix does help with real spare CPU

Task #243 measured this fix as having "smaller than expected and mixed"
impact and explicitly flagged that conclusion as unreliable given the
2-vCPU sandbox couldn't demonstrate what offloading buys once real spare
capacity exists. With double the CPU, it does:

| Metric | Baseline (2 vCPU) | With fix (2 vCPU, run2) | This run (4 vCPU) |
|---|---|---|---|
| Login median | 5.2s | 8.9s | **0.9s** |
| Login average | 7.1s | 8.6s | **1.85s** |
| Login max | 28.2s | 18.0s | **10.8s** |

A ~6-9x improvement in login latency once the offloaded bcrypt work
actually has a spare core to run on, instead of still fully competing for
the same 2 cores as everything else. This confirms task #243's own
prediction and closes out the "should this be re-measured" question from
that report -- yes, and it clearly helps.

## Headline finding 2 (concerning): bulk sales upload jobs failed almost completely under this load

| | Baseline (2 vCPU) | This run (4 vCPU) |
|---|---|---|
| `/sales/upload` end-to-end requests | 236 | 145 |
| Failures | **0** | **143 (98.6%)** |
| Median completion | 27s | 145s (dominated by the failures below) |

Every failure is the same error, from `backend/loadtest/locustfile.py`'s
poll loop (60 attempts, ~1s apart): `TimeoutError('job ... did not reach a
terminal status within 60 poll attempts')`. This is not a capacity
regression from more concurrent traffic in the abstract -- it traces to a
specific, identifiable cause: **`BULK_UPLOAD_MAX_CONCURRENT_JOBS = 2`**
(`backend/src/core/config.py`), added in task #255 *after* task #243's
original baseline run, so it was never load-tested against realistic
concurrency until now.

`_BULK_UPLOAD_SEMAPHORE = asyncio.Semaphore(settings.BULK_UPLOAD_MAX_CONCURRENT_JOBS)`
(`backend/src/sales/service.py`) is a module-level object, instantiated
once per Python process. `docker-compose.loadtest.yml` (matching
`docker-compose.prod.yml`) runs `--workers 2` gunicorn workers, each a
separate process -- so the *real* system-wide concurrent-upload capacity
is 2 workers × 2 slots = **4 concurrent bulk uploads, total, across the
entire app**, not per-business or per-worker-scaled. With 30 simulated
businesses each periodically submitting bulk uploads over a 6-minute run,
demand vastly exceeds that 4-slot ceiling; jobs queue behind the
semaphore, and each poll request itself also slows down under the
resulting contention (the observed 145s median / 172s max end-to-end
times are consistent with a 60-iteration poll loop where individual polls
increasingly compete for the same 4 gunicorn worker slots, not just the
semaphore itself).

**From a real trader's perspective, this means a CSV import can appear to
hang indefinitely** under the exact "dozens of concurrent businesses"
concurrency this task was asked to validate at -- not a crash, but
functionally broken for the person waiting on it. Task #255's fix was
correct for its own original goal (bound a *single business's* burst of
concurrent uploads so it can't exhaust worker/DB resources by itself) but
the chosen limit is far too low for realistic *cross-business* launch-day
concurrency.

**Action**: filed as a new follow-up task rather than fixed in this
load-test re-run -- the right fix needs a real decision (raise the limit
to something concurrency-appropriate? make it a shared Redis-based
semaphore so it's genuinely global across workers instead of
per-process-multiplied? decouple background-job capacity from foreground
request-serving capacity entirely, per task #243's own already-filed
finding #2 about this exact contention?), not a one-line config bump
guessed at under time pressure.

## Other endpoints: roughly comparable to baseline, some regressed

Dashboard, products, sales-list, and reports endpoints did *not* show the
dramatic improvement login did -- some (dashboard 90th %ile: 3.8s → 5.1s;
reports median: 1.4s → 2.2s) were mildly worse than the 2-vCPU baseline
despite more CPU being available. The likely explanation is throughput,
not capacity: this run completed 57.1 req/s aggregate vs. baseline's
51.0 req/s -- more total work got done in the same 6 minutes (consistent
with login's big speedup unblocking more request flow generally), which
means more concurrent load on the same `DB_POOL_SIZE=15` /
`DB_MAX_OVERFLOW=25` pool (task #228, already fixed from 10/20) at any
given instant. Worth another look once bulk-upload's concurrency issue
(finding 2) is fixed and doesn't distort overall system load, but not
alarming on its own.

## What this confirms from task #243

- The bcrypt `asyncio.to_thread` fix (finding #3 in the original report):
  **confirmed to meaningfully help**, closing out that report's open
  question.
- Task #228 (DB pool headroom): stayed fixed, no `QueuePool` timeout
  failures reappeared in this run despite higher throughput.
- A **new, previously-undetected regression** was found: task #255's
  bulk-upload concurrency semaphore is far too restrictive for real
  launch-scale concurrency. This is exactly the kind of finding
  Hetzner-class re-testing was meant to surface -- not just "are the
  absolute numbers better," but "does a fix made in isolation hold up
  under realistic concurrent load."

## Caveats

- Still not real Hetzner hardware -- 4 vCPU/4GB Colima is a local
  approximation, not a measured production number. Directional
  improvement (login) and the structural bug (finding 2) are both
  real regardless of the exact hardware; absolute latency numbers still
  aren't a literal production prediction.
- This run's failures are now dominated by finding 2 rather than raw
  capacity, which makes the "other endpoints" comparison (previous
  section) noisier than task #243's original -- worth re-running once
  the concurrency limit is fixed, for a cleaner signal.

## Reproducing this test

Same as task #243's reproduction steps
(`.taskmaster/docs/loadtest-findings-243.md`), plus reconfiguring Colima
first:

```bash
colima stop && colima start --cpu 4 --memory 4
docker compose -f docker-compose.loadtest.yml up -d --build
docker compose -f docker-compose.loadtest.yml exec backend_loadtest alembic upgrade head
DATABASE_URL=postgresql+asyncpg://modishlog:modishlog_dev@localhost:5436/modishlog_loadtest \
  SECRET_KEY=loadtest-only-secret-key-not-for-real-use \
  UPLOAD_DIR=/tmp/modishlog_uploads \
  backend/.venv/bin/python backend/scripts/loadtest_seed.py
backend/.venv/bin/locust -f backend/loadtest/locustfile.py --host http://localhost:8010 \
  --users 200 --spawn-rate 5 --run-time 6m --headless \
  --csv backend/loadtest/results/run3_4cpu
docker compose -f docker-compose.loadtest.yml down -v
colima stop && colima start --cpu 2 --memory 2   # restore original local config
```
