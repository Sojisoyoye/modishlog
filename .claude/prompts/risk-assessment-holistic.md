# ModishLog — Holistic Risk Assessment (Security, Ethical, Reliability)

**Exercise Goal**: Perform a holistic risk assessment covering security, ethics, and reliability
dimensions specific to ModishLog — a multi-tenant SMB trade intelligence and inventory management
platform serving importers in Nigeria and Sub-Saharan Africa.

---

```xml
<task>
Complete risk assessment: security, ethical, and reliability dimensions for ModishLog —
a FastAPI + Angular platform that manages FX exposure, AI-driven pricing/reorder
recommendations, inventory, sales, purchase orders, and cashflow for SMB importers
operating in volatile-currency markets (NGN/USD, EUR/USD).
</task>

<platform_context>
  <stack>
    Backend  : Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + Alembic + PostgreSQL
    Frontend : Angular 21 (standalone, Signals, OnPush) + TailwindCSS v4 + PrimeNG v21
    AI/ML    : Prophet (demand forecasting) + NumPy/SciPy (Monte Carlo FX simulation)
               + scikit-learn + Anthropic Claude API (recommendations)
    Auth     : JWT (python-jose) in HttpOnly cookies + bcrypt (passlib) + refresh tokens
    Infra    : Docker + Hetzner VPS (production) + Neon PostgreSQL (staging) + Vercel
               + GitHub Actions CI/CD + Sentry (error tracking, PII scrubbing)
    Security : slowapi rate limiting (in-memory, per-worker) + SecurityHeadersMiddleware
               (CSP/HSTS/X-Frame-Options) + Fernet-encrypted API keys in DB
  </stack>

  <domains>
    auth        — JWT + bcrypt, role-based (Admin / Sales Manager / Owner), account lockout
    products    — CRUD, categories, image uploads, SKU, price suggestion engine
    sales       — Daily entry, FIFO COGS, bulk CSV upload, audit trail, quick quote
    inventory   — Stock levels, low-stock alerts, FIFO batch tracking, depletion forecast
    orders      — Purchase order lifecycle (6 statuses), lot tracking, payment recording
    fx          — Multi-currency exposure (NGN/USD + EUR/USD), 180-day Prophet+Monte Carlo
                  forecast, live rate cache (4-hour TTL, ExchangeRate-API), FX alerts
    cashflow    — 6-month rolling projection, DSCR, triage mode, stress scenarios
    pricing     — Demand elasticity (Prophet), margin optimisation (scipy), price suggestion
    ai_engine   — Unified AI recommendations: pricing/inventory/FX/cashflow/reorder,
                  USD accumulation strategy, Anthropic Claude integration
    customers   — Customer records linked to sales and business
    suppliers   — Supplier records linked to orders
    settings    — Per-user Anthropic API key (Fernet-encrypted), preferences
    data_import — ETL migration framework (CSV + live API extraction) [planned]
  </domains>

  <data_sensitivity>
    - Business financial data: sales revenue, margins, COGS, profit/loss
    - FX exposure: outstanding USD/EUR obligations per order (commercially sensitive)
    - Supplier pricing: per-unit costs and landed costs (trade secrets)
    - Customer data: names, emails, phone numbers (NDPR-regulated PII)
    - AI-generated recommendations: pricing strategy, reorder timing, FX hedging
    - Anthropic API keys: encrypted at rest per user via Fernet
    - Bank/payment references on purchase orders and expenses
    - Historical migration data from external POS systems (full transaction history)
  </data_sensitivity>

  <regulatory_context>
    - NDPR (Nigeria Data Protection Regulation) — equivalent to GDPR, covers customer PII
    - CBN (Central Bank of Nigeria) — regulations on FX transactions and reporting
    - FIRS (Federal Inland Revenue Service) — VAT and tax obligations on sales
    - No HIPAA, but business financial data carries significant commercial liability
    - NDPR penalties: up to 2% of annual gross revenue or ₦10,000,000 (whichever is higher)
  </regulatory_context>
</platform_context>

<assessment_framework>
  <security_risks>
    - Authentication and session management
      (JWT in HttpOnly cookie vs refresh token in JSON response body,
       account lockout bypass, token revocation on logout)
    - Rate limiting architecture
      (slowapi in-memory storage — per-gunicorn-worker, not shared across workers,
       easily bypassed at 2× limit with 2 workers)
    - Input validation and injection
      (SQLAlchemy ORM used throughout — raw SQL forbidden by convention,
       but bulk CSV upload and migration ETL parse untrusted input)
    - File upload security
      (product image uploads: MIME type validation, path traversal, storage isolation)
    - API key management
      (Anthropic key Fernet-encrypted in DB; ExchangeRate-API key in env var;
       Fernet master key rotation strategy undefined)
    - CSP with unsafe-inline
      (Angular runtime requires 'unsafe-inline' — deferred post-MVP, known gap)
    - Business data isolation
      (every query must filter by business_id; cross-tenant data leakage risk
       if a single query omits the business_id WHERE clause)
    - Migration credential handling
      (pos_migrate.py / ETL API extractor receives source-system credentials —
       must never log or persist them)
    - Dependency supply chain
      (pip-audit CVE scan in CI; cryptography, python-jose, passlib must stay current)
    - Secret management in CI/CD
      (HETZNER_SSH_KEY, STAGING_DATABASE_URL, STAGING_SECRET_KEY, VERCEL_TOKEN
       stored as GitHub Actions secrets — rotation cadence undefined)
  </security_risks>

  <ethical_risks>
    - AI pricing recommendations on vulnerable SMB populations
      (Prophet demand model + scipy optimisation produces "minimum viable sell price"
       recommendations for traders with thin margins — overconfident recommendations
       could cause under-pricing or over-pricing against local market conditions)
    - FX-driven reorder bias
      (AI reorder suggestions weighted by USD/NGN rate volatility — could push
       businesses toward over-ordering in USD when NGN is temporarily strong,
       increasing debt exposure on a reversal)
    - Monte Carlo FX forecasting overconfidence
      (180-day Prophet + Monte Carlo simulation presented with confidence intervals —
       confidence intervals may be underestimated for a market as volatile as NGN/USD,
       leading businesses to make large FX commitments based on spurious precision)
    - DSCR threshold hard-coding
      (debt service coverage ratio thresholds defined in code may not reflect Nigerian
       SMB financial realities — flagging healthy businesses as at-risk)
    - Triage mode automated recommendations
      (automated "delay supplier payment" or "liquidate stock" recommendations
       could damage supplier relationships or trigger supply chain disruption
       without human review)
    - Demand elasticity model trained on sparse data
      (Prophet requires ≥10 data points — businesses with thin sales history get
       recommendations from under-trained models; no fallback indicator shown to user)
    - Cross-subsidisation display
      (showing which products subsidise others could be used to make decisions that
       harm low-margin product lines which may be community staples)
    - Customer data used in AI context
      (customer names/emails stored — must not be sent to Anthropic API without consent)
    - Algorithmic recommendations without explanation
      (AI recommendations show priority score but limited explanation of how the
       score was computed — opacity reduces user ability to challenge bad advice)
    - Single-business data training
      (all ML models trained on one business's own data — limited sample size means
       statistical conclusions may be unreliable but presented with false authority)
  </ethical_risks>

  <reliability_risks>
    - CPU-bound ML in async event loop
      (Prophet training and scipy optimisation are CPU-intensive — if not run in
       asyncio.to_thread, they block the event loop and starve all other requests)
    - External API dependencies without circuit breakers
      (ExchangeRate-API and Anthropic API called via httpx — no circuit breaker,
       no timeout enforced on all call sites, failures propagate to user-facing endpoints)
    - FX live rate cache failure
      (4-hour DB-cached live USD/NGN rate — if ExchangeRate-API is down AND cache
       is stale, price suggestion engine may use DEFAULT_FX_RATE = 1500 NGN/USD
       which could be wildly incorrect at time of use)
    - In-memory rate limiter state loss
      (slowapi uses in-memory storage — rate limit counters reset on container restart,
       enabling burst attacks immediately after deploys or crashes)
    - No Redis dependency
      (session state, rate limiting, and job progress all in-memory — no persistence
       across restarts, no sharing across multiple backend instances)
    - Neon PostgreSQL cold starts on staging
      (serverless Neon DB has cold start latency — first request after idle period
       may timeout, causing misleading errors in staging validation)
    - Monte Carlo memory pressure
      (NumPy Monte Carlo simulations with 10,000 paths over 180 days —
       concurrent simulation requests could exhaust container memory)
    - Bulk CSV upload without streaming
      (large CSV files loaded into memory — no row-by-row streaming,
       potential OOM for files with 10,000+ rows)
    - Migration job durability
      (ETL migration jobs run in a single async transaction — no checkpoint/resume,
       a crash mid-migration requires full restart and risks partial state)
    - Database connection pool unconfigured
      (SQLAlchemy async engine uses default pool size — no explicit pool_size or
       max_overflow set, could exhaust DB connections under load)
    - Cascade failure from Sentry
      (if Sentry DSN is misconfigured, exception handling paths that call Sentry
       could raise secondary exceptions masking the original error)
    - Single-server production deployment
      (one Hetzner VPS running both nginx and backend — no load balancer,
       no redundancy, hardware failure = total outage)
  </reliability_risks>
</assessment_framework>

<risk_matrix>
For each identified risk, assess:
- Dimension     : Security / Ethical / Reliability
- Severity      : Critical / High / Medium / Low
- Likelihood    : High / Medium / Low
- Impact Domain : Business Owner / Customers / Suppliers / Competitors / Regulators / Platform
- Interconnections : How this risk interacts with risks in other dimensions
- NDPR / CBN Compliance Impact : Regulatory category if applicable

Example interconnections to trace:
- Rate limiter bypass (Security) → brute-force login → account takeover →
  all business financial data exposed (Security→Security)
- FX forecast overconfidence (Ethical) → over-ordering decision →
  cashflow stress scenario triggered → triage recommendations fire →
  automatic supplier payment delay (Ethical→Reliability→Ethical)
- Migration credential exposure (Security) → source-system credentials leaked →
  competitor access to prior business data (Security→Ethical)
- Prophet model under-training (Ethical) → bad reorder suggestion →
  stockout → sale loss not reflected in P&L until next reporting period (Ethical→Reliability)
</risk_matrix>

<modishlog_specific_context>
- Primary users are Nigerian SMB importers — financially vulnerable, operating in
  a high-volatility FX environment with thin margins
- A bad AI recommendation (pricing, reorder, FX) has direct, immediate financial
  consequences for the business owner — this is not advisory, it is operational
- Customer and supplier PII falls under NDPR — a data breach carries regulatory
  penalties and reputation damage in a relationship-driven market
- The platform currently runs on a single Hetzner VPS — no HA, no failover
- Staging uses Neon (serverless), production uses Docker + local PostgreSQL
- GitHub Actions is the sole CI/CD pipeline — a compromised workflow secret
  gives full production deployment access
- All financial computations use Python Decimal (NUMERIC 18,6 in DB) —
  floating-point errors are excluded by design but must be verified
- The Anthropic API key per user is the highest-value secret in the system —
  misuse could incur significant cost to the business owner
</modishlog_specific_context>
```
