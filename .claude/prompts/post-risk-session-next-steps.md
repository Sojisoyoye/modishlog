# Post-Risk Session — Next Steps (Jul 8 2026)

The risk-session-bootstrap.md cycle is fully complete as of 2026-07-08.
PR #270 merged. 25/33 risks fixed. 1193 tests passing. 8 deferred items → tickets #165–172.

Use the prompts below to continue in a new session. Run them in order.

---

## Prompt A — Deploy to production (do this first)

```
Prod PostgreSQL has 2 missing columns found in the Jul 8 schema diagnostic.
Before deploying:

1. Go to GitHub Actions → run the "Fix Prod Schema" workflow (fix-prod-schema.yml)
   manually via workflow_dispatch. Wait for it to succeed.
   It adds: products.image_url VARCHAR(500) and sales.sell_price_ngn NUMERIC(18,6).

2. Then deploy by pushing a version tag:
     git tag v1.0.0 && git push origin v1.0.0
   OR trigger deploy-production.yml via workflow_dispatch with:
     image_tag = main
     confirm  = deploy-production

3. After deploy, verify:
     curl https://api.modishlog.com/health        → 200
     curl https://api.modishlog.com/health/deep   → {"status":"healthy",...}

The prod DB is currently at alembic revision a46ec11f3501.
The deploy runs alembic upgrade head which advances it to 4def4e1d8faf.
```

---

## Prompt B — NDPR consent (task #168, HIGH — legal requirement before accepting users)

```
Implement NDPR consent capture on the onboarding flow. Task #168.

Backend (TDD — write tests first):
- Add ndpr_consent_given: bool and ndpr_consent_at: datetime to User model
  in backend/src/auth/models.py. Create an Alembic migration.
- Add ndpr_consent: bool (required) to OnboardRequest schema
  in backend/src/auth/schemas.py. Return HTTP 422 if False.
- Store consent timestamp in create_business_and_owner()
  in backend/src/auth/service.py.
- Tests: POST /auth/onboard without ndpr_consent → 422.
         POST /auth/onboard with ndpr_consent=true → 201, user.ndpr_consent_given=true.

Frontend:
- Add a required checkbox to the Angular onboarding wizard
  (frontend/src/app/features/auth/) on step 1:
  "I consent to ModishLog processing my business data as required by the
   Nigeria Data Protection Regulation (NDPR). [Privacy Policy]"
  The Next/Submit button must be disabled until the checkbox is checked.
- Playwright E2E: assert checkbox is present, required, and blocks progression.

Branch: feat/168-ndpr-consent
Open PR after all tests pass. Run /review before merging.
```

---

## Prompt C — Ops tasks (tasks #170 + #171, HIGH — before launch)

```
Two ops tasks to complete before production launch:

Task #170 — Production restore drill (docs/ops/backup-restore-runbook.md):
1. SSH into Hetzner and take a pg_dump of the prod DB:
     docker compose exec db pg_dump -U postgres modishlog | gzip > modishlog-$(date +%Y%m%d).sql.gz
2. Create a test container and restore the dump into it.
3. Run spot-check: SELECT count(*) FROM products; SELECT count(*) FROM sales;
4. Verify row counts match the source. Note the wall-clock time.
5. Stop and remove the test container.
6. Record the drill outcome in docs/ops/backup-restore-runbook.md under
   a "## Drill Log" section: date, operator, RTO achieved, result (PASS/FAIL).
7. Commit the updated runbook.

Task #171 — UptimeRobot monitoring:
1. Set up monitors at uptimerobot.com:
   - HTTP(S) monitor for https://api.modishlog.com/health — every 5 minutes
   - HTTP(S) monitor for https://modishlog.com — every 5 minutes
   - Alert contact: soji.soyoye@gmail.com on 2 consecutive failures
2. Save a screenshot of the dashboard (both monitors green) to
   docs/ops/uptime-monitoring-setup.png
3. Update docs/ops/backup-restore-runbook.md with the UptimeRobot dashboard URL.
4. Commit both files.
```

---

## Prompt D — Deferred risk tickets (tasks #165–167, #169, #172, MEDIUM)

```
Work through the remaining 5 medium-priority deferred risk tickets from the
Jul 8 risk session. Run task-master next to get the highest-priority one.

Summary of what each ticket covers:

#165 — Add fx_rate_stale: bool and fx_rate_source: str to SellingPriceSuggestionResponse.
       Show a yellow "Using cached FX rate" badge in the Angular pricing page when stale.

#166 — Add ai_available: bool and degraded_reason: str to recommendation list response.
       Show an amber banner in the Angular recommendations page on AI outage.

#167 — Apply the same MAX_CSV_ROWS (50,000) streaming row limit that products bulk upload
       uses to the sales bulk upload endpoint (if one exists).

#169 — When a product has < 10 sales, the backend returns InsufficientPriceDataError (400).
       Show a friendly "Not enough data yet — record at least 10 sales" empty state in
       the Angular pricing page instead of a generic error.

#172 — Wrap the SciPy optimize.minimize() call in pricing/service.py in
       asyncio.wait_for(..., timeout=30.0) matching the Prophet/Monte Carlo pattern.
       Catch asyncio.TimeoutError → raise ForecastTimeoutError("SciPy optimization", 30.0).
       Ensure the pricing router returns HTTP 504 on this error.

TDD for all backend changes. Branch + PR per ticket. Run /review before merging.
```
