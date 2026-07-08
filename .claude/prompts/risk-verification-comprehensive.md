# ModishLog — Comprehensive Risk Verification

**Exercise Goal**: Verify that all security, ethical, and reliability mitigations are
correctly implemented and integrated across ModishLog. Each item maps to a specific
file, endpoint, or behaviour that can be directly observed or tested.

---

```xml
<task>
Verify integrated risk mitigation across all dimensions for ModishLog.
For each checklist item: identify the file/endpoint to inspect, the test command
or observation method, and the expected result. Mark PASS, FAIL, or NOT IMPLEMENTED.
</task>

<verification_matrix>

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- SECURITY VERIFICATION                                                   -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  Security — Authentication and Session Management:
  - [ ] JWT access token set as HttpOnly cookie on login (not only in JSON body)
        File   : backend/src/auth/router.py → login()
        Check  : curl -v POST /api/v1/auth/login → response headers contain
                 Set-Cookie: access_token=...; HttpOnly; SameSite=Lax
        Expected: HttpOnly flag present, Secure flag present in non-dev environments

  - [ ] Refresh token NOT readable by JavaScript (HttpOnly cookie or excluded from
        JSON body)
        File   : backend/src/auth/router.py → TokenResponse
        Check  : Response body of /login — refresh_token should not appear in JSON
                 if moved to HttpOnly cookie (or if still in body, document the risk)
        Expected: Either HttpOnly cookie OR risk documented and accepted

  - [ ] Account lockout fires after 5 failed logins, not before
        File   : backend/src/auth/service.py → authenticate_user()
        Test   : pytest tests/test_auth.py -k "lockout"
        Expected: 5th failure triggers lockout, 4th does not

  - [ ] Logout revokes refresh token in DB and clears cookie
        File   : backend/src/auth/router.py → logout()
        Test   : POST /logout with valid refresh_token → GET /me returns 401
        Expected: 401 on subsequent authenticated request

  - [ ] Password reset token expires and is single-use
        File   : backend/src/auth/models.py → PasswordResetToken.used + expires_at
        Test   : pytest tests/test_auth.py -k "reset_token"
        Expected: Second use of same token returns 400

  - [ ] bcrypt used for all password hashing (not MD5/SHA1)
        File   : backend/src/auth/service.py
        Grep   : grep -r "CryptContext" backend/src/auth/ — must show bcrypt scheme
        Expected: schemes=["bcrypt"], deprecated="auto"

  Security — Rate Limiting:
  - [ ] Auth endpoints rate-limited at configured threshold
        Endpoint: POST /api/v1/auth/login
        Test   : Send 11 requests in 1 minute → 11th returns 429
        Expected: HTTP 429 with Retry-After header

  - [ ] Rate limiter shares state across workers (Redis) in production
        File   : backend/src/core/rate_limit.py
        Check  : Limiter initialisation uses storage_uri when ENVIRONMENT=production
        Expected: storage_uri="redis://redis:6379" (or equivalent) for non-dev

  - [ ] Public onboarding endpoint rate-limited (5/min)
        Endpoint: POST /api/v1/auth/onboard
        Test   : Send 6 requests in 1 minute → 6th returns 429

  Security — Input Validation and Injection:
  - [ ] No raw SQL in service files (only in Alembic migrations)
        Grep   : grep -rn "text(" backend/src/ --include="*.py" | grep -v alembic
        Expected: Zero matches outside alembic/

  - [ ] Business ID filter present on every domain query
        Method : Run the cross-tenant isolation test suite
        Test   : pytest tests/ -k "cross_tenant" or "business_isolation"
        Expected: Business A cannot retrieve Business B's products, sales, customers,
                  orders, FX data, or AI recommendations

  - [ ] Bulk CSV upload validates input before processing
        Test   : Upload a CSV with SQL injection payload in a name field
                 e.g., name="'; DROP TABLE products; --"
        Expected: Data stored as literal string, no DB error, no data loss

  Security — File Uploads:
  - [ ] MIME type validated server-side (not from Content-Type header)
        File   : backend/src/products/service.py or router.py
        Test   : Upload a PHP file renamed to image.jpg with Content-Type: image/jpeg
        Expected: HTTP 400 — rejected by python-magic MIME check

  - [ ] Uploaded files served from isolated storage, not web root
        File   : nginx/nginx.prod.conf + docker-compose.prod.yml
        Check  : UPLOAD_DIR=/app/uploads not under /usr/share/nginx/html
        Expected: /static/ location in nginx aliases /app/uploads/, not inline

  Security — API Key Management:
  - [ ] Anthropic API key stored encrypted (Fernet) in DB, not plaintext
        File   : backend/src/settings/models.py → UserApiKey.encrypted_value
        Test   : SELECT encrypted_value FROM user_api_keys LIMIT 1 → starts with "gAAAA"
                 (Fernet token prefix)
        Expected: Encrypted value, not raw API key string

  - [ ] SECRET_KEY validation rejects weak/default values
        File   : backend/src/core/config.py → validate_secret_key()
        Test   : Set SECRET_KEY="dev-secret-change-in-production", start app
        Expected: ValueError raised at startup, app does not start

  - [ ] No secrets in application logs
        Method : Search structlog output for sensitive field names
        Grep   : grep -r "password\|secret_key\|api_key\|encrypted_value" \
                 backend/src/ --include="*.py" | grep "log\.\|logger\."
        Expected: Zero matches (secrets never passed to logger)

  Security — Transport and Headers:
  - [ ] HSTS header present on all HTTPS responses
        Check  : curl -I https://modishlog.com | grep Strict-Transport-Security
        Expected: max-age=31536000; includeSubDomains

  - [ ] X-Frame-Options: DENY on all responses
        File   : backend/src/core/middleware.py
        Check  : curl -I https://modishlog.com/api/health | grep X-Frame-Options
        Expected: DENY

  - [ ] CORS wildcard origin rejected at startup
        File   : backend/src/core/config.py → reject_wildcard_origins()
        Test   : Set CORS_ORIGINS="*", start app
        Expected: ValueError raised, app does not start

  Security — CI/CD and Dependencies:
  - [ ] pip-audit CVE scan blocks merge on unfixed vulnerabilities
        File   : .github/workflows/_dependency-scan.yml
        Check  : pip-audit invocation includes --fail-on-vuln flag
        Expected: Workflow fails if any unfixed HIGH/CRITICAL CVE found

  - [ ] Docker images do not run as root
        File   : backend/Dockerfile
        Check  : Dockerfile contains USER appuser (or non-root USER)
        Expected: Non-root user in final stage

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- ETHICAL VERIFICATION                                                    -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  Ethical — AI Recommendation Transparency:
  - [ ] Every AIRecommendation includes data_points_used and confidence_reliable
        File   : backend/src/ai_engine/schemas.py → AIRecommendationRead
        Test   : GET /api/v1/ai/recommendations → each item has data_points_used: int
                 and confidence_reliable: bool
        Expected: Both fields present on every recommendation object

  - [ ] Frontend shows "Low confidence" badge when confidence_reliable = false
        File   : frontend/src/app/features/ai-engine/ (recommendations component)
        Test   : Create a product with <10 sales, trigger recommendation,
                 view in UI → badge visible
        Expected: Warning badge visible, recommendation not suppressed but labelled

  - [ ] Every recommendation has reason_summary and evidence fields
        File   : backend/src/ai_engine/schemas.py
        Test   : GET /api/v1/ai/recommendations → reason_summary is non-empty string,
                 evidence is list with 2–4 items
        Expected: Non-empty, human-readable explanation present on all recommendations

  Ethical — Pricing Fairness:
  - [ ] Price suggestion never returns a value below FIFO landed cost
        File   : backend/src/pricing/service.py
        Test   : pytest tests/test_pricing.py -k "price_floor"
        Method : Configure product where scipy optimum is below cost, call
                 GET /api/v1/pricing/suggest
        Expected: PricingSuggestionError raised OR floor applied with warning logged

  - [ ] Price suggestion discloses when it uses a stale or default FX rate
        File   : backend/src/pricing/service.py + schemas
        Test   : Call /pricing/suggest with ExchangeRate-API mocked as down
        Expected: Response includes fx_rate_stale: true or warning message

  Ethical — FX Forecasting:
  - [ ] FX Monte Carlo response includes forecast_disclaimer field
        File   : backend/src/fx/service.py + schemas
        Test   : POST /api/v1/fx/simulate → response body contains forecast_disclaimer
        Expected: Non-empty disclaimer string about model limitations

  - [ ] Volatility multiplier > 1.0 applied for NGN/USD simulations
        File   : backend/src/fx/service.py
        Test   : pytest tests/test_fx.py -k "volatility_multiplier"
        Expected: Confidence intervals wider than raw Gaussian output

  Ethical — Human Review Gates:
  - [ ] DELAY_PAYMENT and LIQUIDATE recommendations require confirmation before apply
        File   : backend/src/ai_engine/router.py → apply recommendation endpoint
        Test   : POST /api/v1/ai/recommendations/{id}/apply with action_type=DELAY_PAYMENT
                 without confirmation flag
        Expected: HTTP 422 with message "Human review required for this action type"

  - [ ] Frontend shows "Review required" badge and confirmation dialog for these types
        File   : frontend recommendations component
        Test   : Playwright E2E — attempt to apply a DELAY_PAYMENT recommendation,
                 confirm dialog appears with consequence description
        Expected: Dialog shown, action only proceeds after explicit user confirmation

  Ethical — Customer PII Protection:
  - [ ] Customer PII (email, name, phone) never sent to Anthropic API
        File   : backend/src/ai_engine/service.py
        Test   : pytest tests/test_ai_engine.py -k "no_pii_in_prompt"
        Method : Mock Anthropic client, capture prompt strings, assert no PII fields
        Expected: Zero occurrences of email/full_name/phone in any captured prompt

  - [ ] NDPR-compliant data retention policy documented and configurable
        File   : docs/ or settings domain
        Check  : Is there a data retention configuration or documented policy?
        Expected: Policy exists; customer data deletion workflow documented

  Ethical — Triage Safeguards:
  - [ ] Triage mode shows cashflow risk rating with threshold source
        File   : backend/src/cashflow/service.py + frontend triage component
        Test   : GET /api/v1/cashflow/triage → response includes
                 dscr_threshold: decimal, threshold_source: string
        Expected: Both fields present, threshold_source references Nigerian SMB norms

  Ethical — Bias Audit Logging:
  - [ ] Recommendation generation logs include category, score, data_points_used
        File   : backend/src/ai_engine/service.py
        Test   : Generate recommendations, check structlog output
        Expected: Each generation event logs business_id (hashed), category,
                  priority_score, data_points_used, model_version

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- RELIABILITY VERIFICATION                                                -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  Reliability — External API Resilience:
  - [ ] ExchangeRate-API outage returns stale cached rate, not 500
        File   : backend/src/fx/service.py
        Test   : pytest tests/test_fx.py -k "stale_rate_fallback"
        Method : Mock httpx.AsyncClient to raise ConnectTimeout
        Expected: Response 200 with stale: true, cached_at timestamp, no 500

  - [ ] Anthropic API outage returns degraded response, not 500
        File   : backend/src/ai_engine/service.py
        Test   : pytest tests/test_ai_engine.py -k "anthropic_unavailable"
        Expected: Response 200 with ai_available: false, empty recommendations list,
                  message: "AI recommendations temporarily unavailable"

  - [ ] External API calls have enforced timeouts (not unlimited)
        File   : backend/src/fx/service.py + ai_engine/service.py
        Grep   : grep -n "timeout" backend/src/fx/service.py backend/src/ai_engine/service.py
        Expected: httpx.AsyncClient initialised with timeout= parameter on all call sites

  Reliability — Event Loop Protection:
  - [ ] Prophet model training runs in asyncio.to_thread()
        File   : backend/src/pricing/service.py
        Grep   : grep -n "to_thread\|run_in_executor" backend/src/pricing/service.py
        Expected: _train_demand_model called via asyncio.to_thread()

  - [ ] Monte Carlo simulation runs in asyncio.to_thread()
        File   : backend/src/fx/service.py
        Grep   : grep -n "to_thread" backend/src/fx/service.py
        Expected: NumPy Monte Carlo loop called via asyncio.to_thread()

  - [ ] ML tasks have a 30-second timeout
        Test   : pytest tests/test_pricing.py -k "forecast_timeout"
        Method : Mock asyncio.to_thread to sleep 35 seconds
        Expected: ForecastTimeoutError raised, not a hanging request

  Reliability — Database:
  - [ ] Connection pool sized explicitly (not SQLAlchemy default)
        File   : backend/src/core/database.py
        Grep   : grep "pool_size\|max_overflow\|pool_pre_ping" backend/src/core/database.py
        Expected: All three parameters set explicitly

  - [ ] pool_recycle set to handle Neon serverless connection drops
        File   : backend/src/core/database.py
        Expected: pool_recycle=3600 (or similar) present

  - [ ] Database health check in /health endpoint
        Test   : GET /api/health → includes db_ok: true/false
        Expected: DB connectivity reflected in health response

  Reliability — Bulk Operations:
  - [ ] CSV bulk upload processes rows in streaming batches (not full memory load)
        File   : backend/src/sales/service.py (bulk upload)
        Test   : Upload 10,000-row CSV → monitor container memory, assert stays < 512MB
        Expected: Memory does not spike to file size × rows

  - [ ] Migration job supports checkpoint/resume after failure
        File   : backend/src/data_import/loader.py (planned)
        Test   : Start 5000-row migration, kill process at row 2500, restart,
                 assert job resumes from row 2500
        Expected: row_counts in job show incremental progress, not full restart

  Reliability — Error Handling:
  - [ ] All domain service functions have try/except around DB operations
        Method : Code review — grep for async def in service files, verify
                 SQLAlchemy exceptions are caught and re-raised as domain exceptions
        Expected: No bare except: pass blocks; all DB exceptions produce structured errors

  - [ ] Sentry PII scrubbing configured for known sensitive fields
        File   : backend/src/core/main.py (Sentry init)
        Test   : pytest tests/test_sentry.py -k "pii_scrubbing"
        Method : Trigger a test exception containing email/password fields,
                 assert Sentry before_send strips them
        Expected: No PII in captured Sentry event payload

  - [ ] 500 errors in production trigger Sentry alert within 60 seconds
        File   : Sentry project alert rules
        Check  : Sentry dashboard → Alerts → "500 error" rule exists
        Expected: Alert rule configured, test notification sent successfully

  Reliability — Infrastructure:
  - [ ] Daily database backup confirmed running
        File   : scripts/backup-db.sh + cron on Hetzner
        Check  : SSH to Hetzner, crontab -l → backup job scheduled
        Expected: Backup runs nightly, retention >= 7 days

  - [ ] Restore drill completed within last 30 days
        File   : docs/db-backup-recovery.md
        Check  : Last restore drill date documented
        Expected: Documented drill date < 30 days ago

  - [ ] Uptime monitoring configured with alert to owner
        Check  : UptimeRobot or equivalent pinging /health every 60s
        Expected: SMS/email alert to business owner on >2-minute outage

  <!-- ═══════════════════════════════════════════════════════════════════════ -->
  <!-- INTEGRATION VERIFICATION                                                -->
  <!-- ═══════════════════════════════════════════════════════════════════════ -->

  Integration — Cross-Dimensional Interactions:
  - [ ] Security breach (token theft) does not expose AI bias audit logs
        Test   : With a stolen read-only token (non-admin), attempt to access
                 /api/v1/ai/audit-logs or similar admin-only audit endpoint
        Expected: 403 Forbidden — audit logs require Admin role

  - [ ] ExchangeRate-API outage (Reliability) does not disable price suggestions
        (the Ethical risk: suggesting wrong prices due to stale FX)
        Test   : Mock ExchangeRate-API as down, request price suggestion
        Expected: Response includes fx_rate_stale: true and recommended action
                  "Verify FX rate before acting on this suggestion"

  - [ ] Anthropic outage (Reliability) does not prevent triage recommendations
        (Ethical: triage must work even when AI is down)
        Test   : Mock Anthropic as down, trigger triage scenario
        Expected: Rule-based triage recommendations still returned (not empty),
                  clearly labelled "AI enhanced recommendations unavailable"

  - [ ] Business isolation failure (Security) is caught by test suite before merge
        Test   : pytest tests/ -k "cross_tenant" — must be in backend-tests.yml CI gate
        Expected: CI fails if any cross-tenant test fails

  - [ ] Migration credential exposure (Security) does not leave credentials in
        any log, DB column, or error response (Reliability interaction)
        Test   : Run a migration job with a deliberately bad password,
                 check structlog output and error response body for credential leakage
        Expected: Error message says "Authentication failed" with no credentials echoed

  Integration — Full Happy Path Verification:
  - [ ] New business onboards → creates products → records sales → sees AI recommendations
        Test   : Playwright E2E test covers end-to-end flow:
                 register → add product → add sale → navigate to AI recommendations
        Expected: All steps complete, recommendations show with confidence and explanation

  - [ ] FX rate goes stale → dashboard shows stale warning → price suggestion warns →
        user sees degraded but functional system (not a 500 page)
        Test   : Set FX cache to expired value, browse dashboard and pricing page
        Expected: Stale rate banner visible, no 500 errors anywhere

  - [ ] Data migration completes → inventory recomputes → AI recommendations refresh
        Test   : Run a test migration (small dataset), verify inventory_levels updated,
                 verify new AI recommendations generated for migrated products
        Expected: Post-migration state consistent with imported transaction history

</verification_matrix>

<modishlog_specific_validation>
  Nigerian Market Compliance:
  - Verify all financial computations use Decimal (grep for float() in service files
    touching monetary values — expect zero matches outside ML/statistics code)
  - Verify NGN is the default currency for new businesses (Business.currency default)
  - Verify FX rate source is acknowledged as indicative (not CBN official rate)
    in any UI element that surfaces FX data used for compliance/tax purposes
  - Verify NDPR consent exists before customer data is stored (registration flow)

  AI Safety for SMB Context:
  - Verify no recommendation can commit the business to a financial obligation
    (order placement, payment) without an explicit owner confirmation action
  - Verify all AI recommendations have an expiry (RECOMMENDATION_EXPIRY_DAYS = 30)
    so stale suggestions do not remain actionable indefinitely
  - Verify a business with zero sales history receives appropriate fallback messaging
    ("Not enough data for AI recommendations — record at least 10 sales to begin")

  Platform Integrity:
  - Verify pytest test count >= 1,018 (as of last known state) — regression check
  - Verify ng build produces 0 errors (not just 0 blocking errors)
  - Verify all Alembic migrations are linear (no branch heads):
    alembic heads — must return exactly one revision
  - Verify no migration has a missing downgrade() implementation for the last 10 revisions
    (rollback capability for production incidents)
</modishlog_specific_validation>
```
