# Post v1.0.0 — Next Steps (Jul 9 2026)

v1.0.0 is live on prod and staging. NDPR consent (task #168) is done.
Run these prompts in order at the start of the next session.

---

## Prompt E — Fix CI/CD gate check with Playwright E2E (do this first)

```
The branch protection on main requires a status check named "gate" before merging.
"gate" is only produced by the backend CI workflow (_dependency-scan.yml → gate job).
Frontend-only PRs never trigger backend CI, so "gate" is never created and every
frontend PR requires --admin to merge, bypassing branch protection.

Fix: Add a real "gate" job to the frontend-build workflow
(.github/workflows/frontend-build.yml) that runs the full Playwright/Chromium E2E
suite. The gate only passes if ALL E2E tests pass — giving frontend PRs meaningful
protection rather than a rubber stamp.

The new gate job should:
1. Depend on the existing "build" job (ng build must pass first)
2. Spin up the full stack via docker compose (backend + db) and wait for /health → 200
3. Run: cd frontend && npx playwright test --project=chromium
4. Be named exactly "gate" so it matches the branch protection requirement
5. Upload the Playwright HTML report as an artifact on failure for easy debugging

Read frontend/playwright.config.ts and the existing e2e setup to match environment
variables and base URL exactly. Check if there is already a CI step that runs e2e
tests elsewhere in the workflows and reuse that pattern.

After the fix:
- Open a small frontend-only PR
- Confirm "gate" appears in the checks and passes with real Playwright output
- Confirm the PR merges without --admin once gate is green
Branch: feat/fix-ci-frontend-gate. PR it, verify, merge.
```

---

## Prompt F — Fix Risk Checks workflow false failures

```
The Risk Checks workflow (.github/workflows/risk-checks.yml) fails on every PR
with two pre-existing false positives that have nothing to do with the code changes:

1. "pip install -r backend/requirements.txt" fails — "No such file or directory"
   The job runs from the repo root but uses a bare filename. Fix: change the path
   to "backend/requirements.txt" in the pip install step (or add
   working-directory: backend to the step).

2. [S2] No raw SQL check false-positives — the grep pattern `text(` matches:
   - os.path.splitext( in backend/src/products/router.py
   - CryptContext(schemes=["bcrypt"]...) in backend/src/core/security.py
   These are not SQLAlchemy text() calls.
   Fix: tighten the grep pattern. Replace the current grep with:
     grep -rn "sqlalchemy.*text\b\|from sqlalchemy import.*\btext\b" backend/src/
   Or use a word-boundary pattern: grep -Pn '\btext\s*\("' to require the opening
   quote that raw SQL always has.

After both fixes, confirm all Risk Checks jobs go green on the next PR.
Branch: feat/fix-risk-checks-workflow. PR, verify, merge.
```

---

## Prompt G — Prod monitoring + provisioning (before first real users)

```
Two items flagged in /health/deep need resolving before real users arrive:

1. Anthropic API key — prod shows `anthropic: error`.
   SSH into Hetzner, add the key to .env.production, restart backend:
     echo 'ANTHROPIC_API_KEY=sk-ant-...' >> /root/modishlog-prod/.env.production
     docker compose --env-file /root/modishlog-prod/.env.production restart backend
   Verify: curl https://api.modishlog.com/health/deep → anthropic should show "ok"

2. Redis — prod shows `redis: not_configured`. Rate limiting falls back to
   in-memory (single-instance only, resets on restart). For MVP this is acceptable
   but document it. Add a Redis container to docker-compose.production.yml and set
   REDIS_URL when ready to scale.

3. UptimeRobot (Task #171 — HIGH):
   - Set up HTTP monitor for https://api.modishlog.com/health — every 5 min
   - Set up HTTP monitor for https://modishlog.com — every 5 min
   - Alert contact: soji.soyoye@gmail.com on 2 consecutive failures
   - Save screenshot of the green dashboard to docs/ops/uptime-monitoring-setup.png
   - Commit the screenshot and update docs/ops/backup-restore-runbook.md with the
     UptimeRobot dashboard URL.
```

---

## Prompt H — Deferred risk tickets (tasks #165–167, #169, #172)

```
Work through the remaining medium-priority deferred risk tickets.
Run: task-master next

Summary:
#165 — Add fx_rate_stale + fx_rate_source to SellingPriceSuggestionResponse.
       Show "Using cached FX rate" badge in the pricing page when stale.

#166 — Add ai_available + degraded_reason to recommendation list response.
       Show amber banner in recommendations page on AI outage.

#167 — Apply MAX_CSV_ROWS (50,000) row limit to sales bulk upload endpoint
       (same cap already on products bulk upload).

#169 — When a product has < 10 sales, backend returns InsufficientPriceDataError (400).
       Show "Not enough data yet — record at least 10 sales" empty state in
       the pricing page instead of a generic error.

#172 — Wrap SciPy optimize.minimize() in asyncio.wait_for(..., timeout=30.0)
       in pricing/service.py. Catch asyncio.TimeoutError → ForecastTimeoutError.
       Pricing router returns HTTP 504 on this error.

TDD for all backend changes. Branch + PR per ticket. Run /review before merging.
```
