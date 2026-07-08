# ModishLog — Integrated Risk Mitigation Design

**Exercise Goal**: Design and implement security, ethical, and reliability mitigations
integrated across all dimensions of ModishLog — a FastAPI + Angular SMB trade intelligence
platform for Nigerian importers.

---

```xml
<role>
Senior full-stack engineer responsible for a financially sensitive, AI-assisted SMB platform
serving Nigerian importers. You must ensure the system is secure against credential and data
theft, ethically responsible in its AI recommendations, and reliable enough for daily
operational use by businesses with no IT team on standby.
</role>

<task>
Design and implement integrated risk mitigations across security, ethics, and reliability
for ModishLog. Each mitigation must name the exact file(s) to change, the specific code
pattern to apply, and how it interacts with mitigations in other dimensions.
</task>

<codebase_anchors>
  Key files most likely to require changes:

  backend/src/core/rate_limit.py       — slowapi limiter (currently in-memory)
  backend/src/core/config.py           — Settings, SECRET_KEY, CORS, JWT config
  backend/src/core/middleware.py       — SecurityHeadersMiddleware (CSP gap)
  backend/src/core/logging.py          — structlog setup (PII scrubbing completeness)
  backend/src/auth/service.py          — bcrypt, lockout, token generation
  backend/src/auth/router.py           — rate limits, cookie security, token response
  backend/src/ai_engine/service.py     — priority scoring, recommendation generation
  backend/src/pricing/service.py       — Prophet demand model, scipy optimisation
  backend/src/fx/service.py            — live rate cache, Monte Carlo, httpx calls
  backend/src/cashflow/service.py      — DSCR thresholds, stress scenario params
  backend/src/inventory/service.py     — low-stock alert thresholds
  backend/src/products/service.py      — image upload handling
  backend/src/data_import/service.py   — ETL pipeline, credential handling [planned]
  backend/src/settings/service.py      — Fernet key management for API keys
  frontend/src/app/core/interceptors/  — HTTP interceptor, auth token handling
  frontend/src/styles.css              — body overflow:hidden (affects auth pages)
  nginx/nginx.prod.conf                — CSP, HSTS, rate limiting at edge
  docker-compose.prod.yml              — container security, resource limits
  .github/workflows/deploy-staging.yml — secret handling, CVE scan
</codebase_anchors>

<integrated_requirements>

  <security>
    1. RATE LIMITER — Replace in-memory slowapi storage with Redis backend
       File: backend/src/core/rate_limit.py
       Change: Limiter(storage_uri="redis://redis:6379") when ENVIRONMENT != "development"
       Why: Two gunicorn workers each allow the full rate before 429 fires.
            Auth endpoints (login, onboard, forgot-password) at 10/min become 20/min
            effective — enough for a credential stuffing attack to succeed.
       Cross-dimension: Reliability (Redis adds a dependency that must be HA)

    2. REFRESH TOKEN EXPOSURE — Move refresh token out of JSON response body
       File: backend/src/auth/router.py + frontend interceptor
       Change: Set refresh_token as a second HttpOnly cookie (SameSite=Strict, Secure,
               Path=/api/v1/auth/refresh). Remove from TokenResponse JSON body.
       Why: Refresh token in JSON response can be read by XSS despite access token
            being in an HttpOnly cookie — the separation is undermined.

    3. CSP unsafe-inline — Implement nonce-based CSP
       File: backend/src/core/middleware.py + nginx/nginx.prod.conf
       Change: Generate a cryptographically random nonce per request, inject via
               middleware, pass to Angular via <meta> tag. Replace 'unsafe-inline'
               with 'nonce-{value}' in script-src and style-src.
       Why: 'unsafe-inline' allows any injected script to execute.
            This is the highest-impact CSP gap.

    4. BUSINESS DATA ISOLATION — Add automated cross-tenant query audit
       File: backend/src/ (all service files that query domain tables)
       Change: Create a SQLAlchemy event listener that asserts every SELECT/UPDATE/DELETE
               on business-scoped tables includes a business_id filter. Raise in tests,
               log warning in production.
       Why: A single missing WHERE business_id = ? clause leaks all tenant data.

    5. FERNET KEY ROTATION — Define key rotation strategy for encrypted API keys
       File: backend/src/settings/service.py + config.py
       Change: Support FERNET_KEYS as a comma-separated list (newest first).
               On read: try each key until decryption succeeds.
               On write: always use the newest key.
               Add /settings/rotate-fernet-key admin endpoint.
       Why: If the Fernet master key is compromised, all stored Anthropic API keys
            are exposed. Rotation must be possible without re-registering keys.

    6. FILE UPLOAD HARDENING — Validate MIME type server-side, isolate storage
       File: backend/src/products/router.py + service.py
       Change: Validate content type via python-magic (not Content-Type header).
               Restrict to image/jpeg, image/png, image/webp only.
               Store uploaded files outside the web root with UUID filenames.
               Never serve user-uploaded content from the same origin as the API.
       Why: Malicious file uploads (SVG with embedded script, PHP shell disguised
            as JPEG) are a common attack vector when MIME type is trusted from headers.

    7. MIGRATION CREDENTIAL SAFETY — Enforce credential zero-persistence in ETL
       File: backend/src/data_import/service.py (planned)
       Change: Credentials passed only in request body. Never log credential fields
               (use structlog.bind with a sanitised context that excludes password/key).
               After extraction completes, explicitly del credentials from local scope.
               Add a test that asserts no credential field appears in any log output.

    8. DEPENDENCY SCANNING — Enforce CVE-free merges
       File: .github/workflows/backend-tests.yml
       Change: pip-audit step already exists — add --fail-on-vuln flag so any
               unfixed CVE blocks merge to main. Pin pip-audit version.
  </security>

  <ethical>
    1. AI RECOMMENDATION CONFIDENCE DISCLOSURE
       File: backend/src/ai_engine/service.py + frontend AI recommendations component
       Change: Every AIRecommendation must include:
               - data_points_used: int (how many sales/FX records trained the model)
               - min_data_threshold: int (project standard minimum)
               - confidence_reliable: bool (data_points_used >= min_data_threshold)
               Frontend: show a "Low confidence — limited data" badge when
               confidence_reliable = False. Do not suppress the recommendation but
               never present it as authoritative.
       Why: Prophet trained on <10 data points produces statistically meaningless
            output presented with the same UI weight as well-trained recommendations.

    2. FX FORECAST UNCERTAINTY BANDS — Widen Monte Carlo confidence intervals
       File: backend/src/fx/service.py (Monte Carlo simulation section)
       Change: NGN/USD exhibits fat-tailed volatility not well-modelled by
               Gaussian Monte Carlo. Add a volatility multiplier (default 1.5×)
               configurable per business. Surface the multiplier in the UI
               ("Forecast uses conservative volatility assumptions").
               Add a disclaimer: "FX forecasts are indicative only. CBN interventions
               and political events can cause moves outside any statistical model."
       Why: Overconfident FX intervals lead businesses to make large USD commitments
            based on spurious precision.

    3. DSCR THRESHOLD LOCALISATION
       File: backend/src/cashflow/service.py
       Change: Replace hardcoded DSCR thresholds (e.g., < 1.25 = danger) with
               configurable per-business values, defaulting to Nigerian SMB norms
               (research-backed). Document the source for the default thresholds.
               Show the threshold and its source in the UI so the business owner
               understands what they're being measured against.

    4. TRIAGE MODE — REQUIRE HUMAN CONFIRMATION BEFORE SUPPLIER ACTIONS
       File: backend/src/cashflow/service.py + frontend triage component
       Change: Triage recommendations of ActionType DELAY_PAYMENT or LIQUIDATE must
               be flagged with requires_human_review = True.
               Frontend: show these with a distinct "Review required" badge.
               The "Apply" button for these action types must show a confirmation
               dialog explaining the consequences before calling the API.
       Why: Automated "delay payment" executed without review can breach supplier
            contracts and destroy trade relationships.

    5. PRICING RECOMMENDATION FLOOR — PREVENT BELOW-COST SUGGESTIONS
       File: backend/src/pricing/service.py + ai_engine/service.py
       Change: Add a hard floor: no price suggestion may recommend selling below
               landed_cost (FIFO COGS + duty + freight). Raise PricingSuggestionError
               if scipy optimisation returns a price below floor.
               Log a warning when the floor is applied so the business can investigate
               their cost structure.
       Why: Demand elasticity optimisation could theoretically produce a loss-making
            price that increases volume — correct economically but ruinous for a
            cash-constrained SMB.

    6. CUSTOMER DATA — NEVER SEND PII TO ANTHROPIC
       File: backend/src/ai_engine/service.py (anywhere Anthropic client is called)
       Change: Audit every Anthropic API call. Customer names, emails, phone numbers
               must never appear in prompts. Use anonymised IDs (customer UUID) only.
               Add a test that mocks the Anthropic client and asserts no PII field
               names appear in the prompt string.

    7. RECOMMENDATION EXPLAINABILITY
       File: backend/src/ai_engine/schemas.py + frontend recommendations component
       Change: AIRecommendation schema must include a reason_summary: str field
               (max 150 chars, human-readable) and evidence: list[str] (2–4 bullet
               points of the data that drove the recommendation).
               Frontend: show reason_summary inline, evidence in an expandable panel.

    8. BIAS AUDIT LOGGING
       File: backend/src/ai_engine/service.py
       Change: Log every generated recommendation with:
               business_id, product_category, recommendation_type, priority_score,
               data_points_used, model_version (date of last training).
               This log is the basis for periodic bias audits to detect if certain
               product categories or business profiles systematically receive
               low-confidence or negative recommendations.
  </ethical>

  <reliability>
    1. CIRCUIT BREAKER FOR EXTERNAL APIS
       File: backend/src/fx/service.py + backend/src/ai_engine/service.py
       Change: Wrap ExchangeRate-API and Anthropic httpx calls with a circuit breaker
               (use tenacity with stop_after_attempt=3, wait_exponential, and a
               fallback that returns a cached value or degrades gracefully).
               FX fallback: use most recent cached DB rate + add a warning flag
               to the response: {"rate": 1580.5, "stale": true, "cached_at": "..."}.
               Anthropic fallback: return a static "AI unavailable — try again later"
               recommendation rather than a 500.

    2. ASYNCIO.TO_THREAD FOR ALL CPU-BOUND ML
       File: backend/src/pricing/service.py + backend/src/fx/service.py
       Change: All Prophet model training (_train_demand_model), scipy.optimize.minimize
               calls, and NumPy Monte Carlo loops must run inside asyncio.to_thread().
               Add a timeout: asyncio.wait_for(asyncio.to_thread(...), timeout=30.0).
               If timeout fires, raise a domain exception (ForecastTimeoutError) and
               return a cached result or a "model busy" response.
       Why: A single sync call on the event loop blocks ALL concurrent requests.

    3. DATABASE CONNECTION POOL — EXPLICIT SIZING
       File: backend/src/core/database.py
       Change: Set pool_size=10, max_overflow=20, pool_pre_ping=True on the async engine.
               Add pool_recycle=3600 to handle Neon serverless connection drops.
               Log pool checkout events at DEBUG level so connection exhaustion
               is visible in logs before it causes 500s.

    4. BULK CSV UPLOAD — STREAMING PARSER
       File: backend/src/sales/service.py (bulk upload) + data_import/etl/extractor.py
       Change: Use csv.reader in a generator that yields rows rather than
               loading the entire file into memory with csv.DictReader on a
               BytesIO object. Process in batches of 500 rows, committing each
               batch separately so a 10,000-row upload doesn't hold a single
               transaction open for minutes.

    5. MIGRATION JOB CHECKPOINT / RESUME
       File: backend/src/data_import/loader.py (planned)
       Change: Store progress in MigrationJob.checkpoint JSONB:
               {"last_entity": "sales", "last_offset": 2300}.
               On restart, skip already-loaded entities and resume from the
               last committed offset. Use SAVEPOINT per entity batch so a
               failure in sales doesn't roll back already-committed products.

    6. HEALTH CHECK — DEEP PROBE
       File: backend/src/health/router.py
       Change: Existing /health does a DB ping. Add /api/health/deep that also:
               - Checks ExchangeRate-API reachability (HEAD request, 2s timeout)
               - Checks Anthropic API key validity (cheapest possible call or key test)
               - Returns degraded (not down) status if external APIs are unreachable
               Used by production monitoring to distinguish DB outage from API outage.

    7. SENTRY PII SCRUBBING — VERIFY COMPLETENESS
       File: backend/src/core/main.py (Sentry init)
       Change: Explicitly configure before_send to strip:
               email, full_name, phone, hashed_password, encrypted_value,
               DATABASE_URL, SECRET_KEY, ANTHROPIC_API_KEY from all Sentry events.
               Add a test that sends a mock exception containing PII fields
               and asserts none appear in the captured Sentry payload.

    8. SINGLE-SERVER HA — DOCUMENT RECOVERY PROCEDURE
       File: docs/deployment.md + docs/db-backup-recovery.md
       Change: Document explicit RTO/RPO targets for the single-Hetzner deployment.
               Add a runbook section: "What to do when the VPS is unresponsive."
               Confirm daily DB backup (backup-db.sh) runs via cron and that
               a restore drill has been performed within the last 30 days.
               Add monitoring: UptimeRobot or similar pinging /health every 60s
               with SMS/email alert to owner.
  </reliability>

</integrated_requirements>

<cross_cutting_concerns>

  <human_in_the_loop>
    Required for the following ModishLog actions before execution:
    - Any AI recommendation with requires_human_review = True
      (triage DELAY_PAYMENT, LIQUIDATE, large FX hedging commitments)
    - Price suggestions below the previous week's sell price by >20%
      (prompt: "This is significantly lower than your recent price — confirm?")
    - Reorder suggestions during a triage-flagged cashflow stress period
      (prompt: "Your cashflow is under stress — do you still want to reorder?")
    - Data migration confirmation (the mandatory snapshot approval screen)
    - Admin actions: deactivate user, reset password, bulk delete

    Clear escalation path: business owner (Admin role) must approve anything
    that could commit the business to a financial obligation or lose data.
  </human_in_the_loop>

  <monitoring>
    Security monitoring (log + alert on):
    - >3 failed logins for any single email within 5 minutes
    - Any request that returns 401/403 for an authenticated user (possible token replay)
    - Any admin endpoint called from an IP that has never authenticated as admin before
    - CSV uploads > 5MB (potential DoS or data exfiltration probe)
    - Fernet decryption failures (possible key rotation issue or tampering)

    Ethical monitoring (log for periodic audit):
    - All AI recommendations generated: type, score, data_points_used, category
    - All price suggestions: suggested price vs current price vs FIFO cost (margin)
    - All FX recommendations: direction, magnitude, current exposure level
    - Recommendations applied vs dismissed ratio per category (detect over-reliance)
    - Cases where confidence_reliable = False was presented to the user

    Reliability monitoring (alert on):
    - /health returning non-200 for >60 seconds
    - DB connection pool exhaustion (pool_checkout > pool_size warning threshold)
    - asyncio.to_thread ML tasks taking >15 seconds (approaching 30s timeout)
    - ExchangeRate-API returning stale rate fallback (notify owner if >8 hours stale)
    - Any 500 error in production (Sentry alert immediate)
    - Container memory usage >80% (Monte Carlo / Prophet OOM risk)

    Integrated compliance dashboard:
    - NDPR readiness: customer PII fields, data retention settings, consent flags
    - Recommendation audit trail: completeness of bias audit logs
    - Security posture: last CVE scan date, open CVEs by severity
    - Backup status: last successful backup, last restore drill date
  </monitoring>

  <testing>
    Security testing:
    - SQLAlchemy ORM compliance: grep for raw text() calls in service files,
      fail build if any found outside migration scripts
    - Business isolation: parametrised test that creates two businesses and asserts
      neither can see the other's products, sales, customers, or AI recommendations
    - Rate limit bypass: send 2× the configured limit across two simulated workers,
      assert at least one request is rejected (requires Redis backend to pass)
    - Fernet rotation: encrypt with key-v1, rotate to key-v2, assert decryption
      succeeds with key-v2 and fails with a completely wrong key
    - File upload: attempt to upload a PHP file with Content-Type: image/jpeg,
      assert 400 returned (MIME magic validation, not header trust)

    Ethical testing:
    - Under-trained model disclosure: create a product with 5 sales,
      request price suggestion, assert confidence_reliable = False in response
    - PII in Anthropic prompts: mock Anthropic client, generate recommendations,
      assert no customer email/name/phone appears in any prompt string
    - Triage human review gate: apply a DELAY_PAYMENT recommendation via API
      without the frontend confirmation flag, assert 422 (requires_confirmation)
    - FX forecast disclaimer: request FX simulation, assert response includes
      disclaimer field and volatility_multiplier > 1.0
    - Pricing floor: configure a product where scipy returns a below-cost price,
      assert PricingSuggestionError is raised and floor is applied

    Reliability testing:
    - ExchangeRate-API outage simulation: mock httpx to raise ConnectTimeout,
      assert FX live rate endpoint returns stale cached value with stale: true,
      not a 500 error
    - Anthropic outage: mock httpx to return 503, assert /ai/recommendations
      returns a degraded response (not 500) with ai_available: false
    - Event loop blockage: run Prophet training synchronously and measure
      response time of a concurrent /health request — must be <100ms
    - Bulk CSV OOM: upload a 50,000-row CSV, assert memory usage stays below
      container limit (streaming validation)
    - Migration resume: start a 10,000-row migration, kill the process at row 5000,
      restart, assert the job resumes from row 5000 not row 0
  </testing>

</cross_cutting_concerns>

<constraints>
  Must comply with:
  - NDPR (Nigeria Data Protection Regulation) — customer PII handling, data retention
  - CBN FX regulations — accurate FX rate sourcing and exposure reporting
  - OWASP Top 10 — injection, broken auth, security misconfiguration, insecure design
  - Python Decimal for all financial values (never float, never approximate rounding)

  Cannot create:
  - Wildcard CORS origins (rejected at config validation layer)
  - Raw SQL outside Alembic migration files
  - AI recommendations without confidence disclosure
  - Price suggestions below FIFO landed cost
  - External API calls that persist credentials

  Must provide:
  - Human review gate for all high-consequence AI actions
  - Business data isolation enforced at query level, not just at route level
  - Audit trail for every financial mutation (sale, order, stock movement, price change)
  - Graceful degradation when Anthropic or ExchangeRate-API is unavailable
  - Explainability fields on every AI recommendation

  Forbidden patterns:
  - print() — use structlog logger
  - float for money — use Decimal
  - git add . — stage specific files only
  - Trust Content-Type header for file MIME validation
  - Log any field named password, key, token, secret, encrypted_value
</constraints>
```
