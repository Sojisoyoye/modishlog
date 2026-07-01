# ModishLog

**Trade Intelligence Inventory Management Software (IMS), Stock Control Software, or an Order Management System (OMS)**

A smart financial co-pilot for importers navigating currency volatility. ModishLog unifies FX forecasting, demand modelling, inventory management, cashflow monitoring, and AI-driven recommendations into a single platform.

---

## Features

### Core Platform
- **Authentication** -- JWT-based auth with HttpOnly cookie (XSS-safe; no token in localStorage), role-based access (Admin / Sales Manager), account lockout with countdown timer, forgot password flow. API key stored encrypted in the database, not in the browser.
- **Dashboard** -- KPI summary banner with 8 metrics (Total Sales, Net Profit, Unpaid Sales, Total Purchased, Amount Owed, Monthly Expenses, Customer Returns, Supplier Refunds) via `GET /dashboard/summary`; location dropdown + date-range filter. Below the KPIs: widget row (Cash Health | Order Activity | Profit Margin), FX row (FX Exposure | Global Exposure), and analytics row (Logistics Efficiency | Stock Levels | Smart Suggestions).
- **Products** -- Full CRUD with categories (two-level hierarchy: parent → sub-category), SKU auto-generation, auto-generated URL slug field, image upload, search/filter, grid/list views, CSV export. Note: `category_id` is NOT NULL — every product must belong to a category. Includes **Price Suggestion** (action menu → Suggest Price): enter a target margin (20–70%), get a recommended sell price based on current landed cost and live FX rate, with suggestion history.
- **Sales** -- Daily entry form with stock validation, CSV bulk upload, edit/delete with audit trail, FIFO cost tracking. Transaction detail lives on a dedicated page (`/sales/transactions/:id`) — breadcrumb, header card (customer, date, status badge), payment summary (including optional `payment_amount` and outstanding balance), inline-editable line items, void and audit per item, and an "Edit Payment & Notes" dialog for transaction-level updates. Includes **Quick Quote** tab: enter a product + quantity to instantly calculate the FIFO-based minimum sell price at a configurable floor margin.
- **Inventory** -- Stock levels, low-stock alerts, batch tracking (FIFO), editable thresholds, depletion forecast with confidence intervals, liquidation candidates
- **Stock Counts** (`/stock-counts`) -- Physical inventory counting sessions with variance reporting. Create a full stock take by product (vs system stock) or by lot (vs purchase order units remaining). Enter counted quantities per row; system snapshots live stock at finalisation and shows variance with colour-coded badges (green = surplus, red = shrinkage). Sessions are locked read-only after finalisation to preserve the audit trail.
- **Orders** -- Full lifecycle pipeline (Ordered → Pending → In Production → Shipping → Cleared → Delivered). Pipeline view at the top of `/orders` acts as a filter — click any status chip to show only those orders in the table; click **All** to reset. All fields (sell price, costs, notes, line items) remain editable even after an order is delivered.

### Order Detail Enhancements
- **Editable sell price per line item** -- Each line item in edit mode has an NGN sell price field. On first save, the current catalog price is locked in so historical profit figures never drift when the catalog changes.
- **Live FX auto-fill** -- Opening a USD order in edit mode with no FX rate auto-fetches the current USD/NGN rate (4-hour cached, sourced from ExchangeRate-API) and pre-fills the field.
- **Lot inventory tracking** -- DELIVERED order detail shows an "In Stock" column per line item — how many units from that purchase lot remain unsold (green if > 0, grey if depleted). Stock deducts FIFO as sales are recorded.
- **Payment recording** -- Record partial or full payments against any order directly from the detail page.

### Financial Intelligence
- **FX Exposure** -- Multi-currency tracking (NGN/USD + EUR/USD), locked/floating exposure per order, cross-rate derivation (EUR/NGN), 180-day forecast with Prophet + Monte Carlo, rate alerts with configurable thresholds
- **Live FX Rate** (`GET /api/v1/fx/live`) -- Current USD/NGN rate with 4-hour DB cache. Backend-only; frontend never calls external APIs directly. Also used by the price suggestion engine.
- **Cashflow** -- 6-month rolling projection, DSCR monitoring, cash runway calculation, liquidity alerts, stress scenarios (FX shock, demand drop, combined), payment calendar
- **Pricing** -- Portfolio margin analysis, per-product margins with target tracking, demand elasticity configuration, cross-subsidisation display, price-FX sensitivity playground with scenario save. Includes **Price Suggestion Engine**: weighted-average lot cost at live FX → minimum viable sell price at a configurable target margin.
- **Global Exposure** -- Multi-currency debt bridge (EUR/USD/NGN), debt-to-trade ratio, currency toggle across panels

### AI & Automation
- **AI Recommendations** -- Unified ranked actions across pricing, inventory, FX, cashflow, and orders with apply/dismiss workflow
- **Logistics Efficiency** -- Shipping + clearing cost as % of COGS, 90-day rolling average, threshold alerts
- **Triage Mode** -- Liquidity squeeze detection with payment calendar, shortfall alerts, ranked corrective actions (liquidate, delay payment, accelerate collection)
- **Quick Quote** -- FIFO-based minimum sell price calculator (Sales page → Quick Quote tab): select product + quantity to get FIFO landed cost, floor margin %, min sell price per unit, and total min price
- **Strategic Mix Planner** -- Target revenue split by product category, actual vs target comparison, drift alerts

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL |
| Frontend | Angular 21 (standalone components, Signals), TailwindCSS v4, PrimeNG v21 |
| AI/ML | Prophet, NumPy/SciPy (Monte Carlo), scikit-learn |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Testing | pytest (722 tests), Playwright E2E (312 tests) |
| Infra | Docker, Docker Compose, Hetzner (SSH), Neon PostgreSQL, Vercel, GitHub Actions |

---

## Project Structure

```
modishlog/
├── backend/
│   ├── src/
│   │   ├── auth/          # Authentication, JWT, roles
│   │   ├── products/      # Product catalog, categories, images
│   │   ├── sales/         # Daily sales, bulk upload, quick quote
│   │   ├── inventory/     # Stock levels, batches, FIFO, liquidation
│   │   ├── orders/        # Purchase orders, pipeline, logistics, lot tracking
│   │   ├── fx/            # FX rates, exposure, forecasting, live rate cache
│   │   ├── cashflow/      # Projections, DSCR, triage, global exposure
│   │   ├── pricing/       # Margins, elasticity, mix targets, price suggestions
│   │   ├── stockcount/    # Physical stock count sessions and variance
│   │   ├── ai_engine/     # Recommendations, USD strategy, reorder
│   │   └── core/          # Config, database, security, logging
│   ├── alembic/           # Database migrations
│   ├── tests/             # 722 pytest tests
│   └── requirements.txt
├── frontend/
│   ├── src/app/
│   │   ├── features/      # 12 page modules (dashboard, sales, products, stockcount, etc.)
│   │   ├── layout/        # Shell, sidebar, topbar
│   │   ├── shared/        # Reusable components
│   │   └── core/          # Services, guards, interceptors
│   ├── e2e/               # Playwright E2E tests
│   └── playwright.config.ts
├── docker-compose.yml
├── CLAUDE.md              # Project rules and conventions
└── README.md
```

Each backend domain follows the same structure:
```
src/<domain>/
├── models.py       # SQLAlchemy 2.0 models (Mapped[], mapped_column)
├── schemas.py      # Pydantic v2 request/response schemas
├── service.py      # Async business logic
├── router.py       # FastAPI routes (thin, no logic)
└── exceptions.py   # Domain-specific exceptions
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 16
- Docker & Docker Compose (optional)

### Option 1: Docker Compose (recommended)

**Requires [Colima](https://github.com/abiosoft/colima) on macOS.**

```bash
make up       # start all services + run migrations (~4 seconds if images exist)
make down     # stop everything
make build    # rebuild images — only needed after requirements.txt / package.json / Dockerfile changes
make logs     # tail all service logs
make test     # run backend pytest suite
make migrate  # run alembic upgrade head manually
make shell    # open a bash shell inside the backend container
make recover  # fix corrupted Docker layers (input/output errors during build) — keeps DB volumes
```

`make up` handles everything: starts Colima if it isn't running, starts containers, and runs migrations. It will be slow the first time (pulls and builds images) but fast on every subsequent run.

**Only run `make build` when dependencies change** — not on every startup. Running `docker compose up --build` every time is what causes multi-minute startups.

### Option 2: Local Development

```bash
# 1. Start PostgreSQL (Docker or local)
docker compose up -d db redis

# 2. Backend
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
UPLOAD_DIR=/tmp/modishlog_uploads \
  DATABASE_URL="postgresql+asyncpg://modishlog:modishlog_dev@localhost:5434/modishlog" \
  SECRET_KEY=dev-secret \
  uvicorn src.main:app --reload --port 8000

# 3. Frontend (in a new terminal)
cd frontend
npm install
npx ng serve --port 4200
```

### First Steps
1. Open http://localhost:4200
2. Register an account on the login page
3. Log in and explore the dashboard
4. Add products via the Products page
5. Record sales, create orders, track FX rates

### Seeding from the live POS (optional)

The `pos_migrate.py` script pulls all products, suppliers, sales, and purchase orders from the live UltimatePOS instance and populates the local DB. **This wipes all existing local data first.**

```bash
# Export POS credentials (never commit these)
export POS_USERNAME=your-pos-username
export POS_PASSWORD=your-pos-password

# 1. Check connectivity and record counts
docker compose exec backend python scripts/pos_migrate.py --step=verify

# 2. Wipe local data + import everything
docker compose exec backend python scripts/pos_migrate.py --step=all

# Individual steps (if you only want one part)
docker compose exec backend python scripts/pos_migrate.py --step=wipe     # clear all local data
docker compose exec backend python scripts/pos_migrate.py --step=migrate  # import without wiping
```

The migration fetches the live USD/NGN rate at import time, converts all NGN purchase amounts to USD, and stores `fx_rate_at_creation` on each purchase order. If you have already imported and need to correct the currency on existing purchase orders without re-running the full migration:

```bash
docker compose exec backend python scripts/patch_po_ngn_to_usd.py --dry-run  # preview
docker compose exec backend python scripts/patch_po_ngn_to_usd.py             # apply
```

---

## Staging Deployment

Staging is **live**. Every push to `main` automatically deploys.

| Component | Service | URL |
|-----------|---------|-----|
| Frontend | Vercel | https://modishlog-staging.vercel.app |
| Backend API | Hetzner server (Docker Compose over SSH) | Set via `STAGING_API_URL` secret |
| API Docs | Swagger UI (staging) | `$STAGING_API_URL/docs` |
| Database | Neon PostgreSQL (staging branch, SSL) | — |
| Registry | GitHub Container Registry (GHCR) | `ghcr.io/sojisoyoye/modishlog/backend:staging` |
| CI/CD | GitHub Actions | `.github/workflows/deploy-staging.yml` |

### Deployment pipeline (triggered on every push to `main`)

1. Run `pytest` against a temporary PostgreSQL container — must pass before any deploy step
2. Build Docker image → push to `ghcr.io/sojisoyoye/modishlog/backend:staging-<sha>`
3. Deploy frontend to Vercel (`npx vercel --prod` — `STAGING_API_URL` substituted via `sed` at build time by `vercel.json` `buildCommand`)
4. SSH into the Hetzner server: pull the new image, run `alembic upgrade head`, restart the backend container, health-check `GET /health` until 200

### Architecture notes

- **Database**: Neon PostgreSQL staging branch. Connection string format: `postgresql+asyncpg://user:pass@ep-xxx-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require`. SSL is auto-configured via `connect_args={"ssl": True}`.
- **Backend host**: Hetzner root server running Docker Compose. The deploy job SSHs in as root, runs `docker-compose pull backend` then `docker-compose up -d --no-deps backend`. Alembic migrations run as a one-off `docker-compose run --rm` before the container swap.
- **Health-check**: CI polls `GET /health` up to 24 times (5 s apart = 2 min) before marking the deploy failed.
- **Frontend env injection**: `STAGING_API_URL` is injected by Vercel's `buildCommand` via `sed` into `environment.staging.ts` at build time — it is not a runtime env var.
- **Azure provisioning scripts**: `infra/azure/setup-staging.sh` is retained for optional Azure Container Apps provisioning but is not used by the current CI pipeline.

### Environment variables reference

See `docs/deployment.md` for the full provisioning guide and `.env.staging.example` for the variable list. Required GitHub Actions secrets:

| Secret | Purpose |
|--------|---------|
| `STAGING_DATABASE_URL` | Neon connection string |
| `STAGING_SECRET_KEY` | JWT signing key (`openssl rand -hex 32`) |
| `STAGING_CORS_ORIGINS` | Allowed frontend origins |
| `STAGING_API_URL` | Backend URL (also set in Vercel dashboard env vars) |
| `HETZNER_HOST` | IPv4 address of the Hetzner server |
| `HETZNER_SSH_KEY` | Private SSH key for root access to the Hetzner server |
| `GHCR_TOKEN` | GitHub PAT (packages:read + packages:write) |
| `VERCEL_TOKEN` | Vercel API token |
| `VERCEL_ORG_ID` | Vercel org ID |
| `VERCEL_PROJECT_ID` | Vercel project ID |

### Re-provisioning from scratch

```bash
# 1. Create Neon project → staging branch → get pooled connection string
# 2. Provision a Hetzner server, install Docker + Docker Compose, place docker-compose.staging.yml
# 3. Set all GitHub Actions secrets (see table above + .env.staging.example)
# 4. Set STAGING_API_URL in Vercel project dashboard (Settings → Environment Variables)
# 5. Push to main — CI/CD handles the rest
```

---

## API Documentation

Interactive API docs are available at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Key Endpoints

| Module | Endpoints |
|--------|-----------|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/forgot-password`, `POST /auth/reset-password` |
| Dashboard | `GET /dashboard/summary` |
| Products | `GET/POST /products`, `PUT/DELETE /products/{id}`, `POST /products/{id}/image`, `GET/POST /products/categories` |
| Sales | `GET/POST /sales`, `PUT/DELETE /sales/{id}`, `POST /sales/upload`, `POST /sales/quick-quote`, `GET /sales/summary`, `POST /sales/daily-entry`, `GET /sales/transactions/{id}`, `PUT /sales/transactions/{id}` |
| Inventory | `GET /inventory`, `POST /inventory/{id}/adjust`, `PUT /inventory/{id}/threshold`, `GET /inventory/batches`, `GET /inventory/batches/liquidation-candidates` |
| Orders | `GET/POST /orders`, `PUT /orders/{id}`, `PUT /orders/{id}/status`, `GET /orders/{id}/lots`, `GET /orders/logistics-efficiency`, `GET /orders/summary` |
| FX | `POST /fx/rates/ingest`, `GET /fx/rates/current`, `GET /fx/live`, `GET /fx/rates/{pair}/history`, `POST /fx/alerts`, `POST /fx/simulate`, `POST /fx/forecast/generate` |
| Cashflow | `GET /cashflow/projection`, `GET /cashflow/dscr`, `GET /cashflow/cash-runway`, `GET /cashflow/global-exposure`, `GET /cashflow/payment-calendar`, `GET /cashflow/triage-status`, `POST /cashflow/triage-check` |
| Pricing | `GET /pricing/portfolio-margin`, `GET /pricing/mix-status`, `POST /pricing/mix-targets`, `POST /pricing/sensitivity-calc`, `GET/POST /pricing/scenarios`, `POST /pricing/suggest/{product_id}`, `GET /pricing/suggest/{product_id}/history` |
| Stock Counts | `GET/POST /stockcount/`, `GET /stockcount/{id}`, `PATCH /stockcount/{id}/items/{item_id}`, `POST /stockcount/{id}/finalize` |
| AI | `GET /ai/recommendations`, `POST /ai/recommendations/generate`, `POST /ai/recommendations/{id}/apply`, `POST /ai/recommendations/{id}/dismiss` |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://modishlog:modishlog_dev@db:5432/modishlog` | PostgreSQL connection string. Accepts `postgres://` / `postgresql://` — the app normalises to `postgresql+asyncpg://` and strips libpq params automatically. |
| `DATABASE_SSL` | *(auto-derived)* | Set to `true` to force SSL on the DB connection. Auto-set when the raw `DATABASE_URL` contains `sslmode=require` or `verify-*`. Required for Neon PostgreSQL in staging/production. |
| `SECRET_KEY` | *(required — no default)* | JWT signing key. Generate with `openssl rand -hex 32`. Server refuses to start without a strong key (≥ 32 chars). |
| `ALGORITHM` | `HS256` | JWT signing algorithm. Only HS256/384/512 accepted — prevents algorithm-confusion attacks. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT access token lifetime in minutes. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime in days. Silently re-issues an access token on expiry without a re-login. |
| `CORS_ORIGINS` | `["http://localhost:4200"]` | Allowed CORS origins (JSON array or comma-separated string). Wildcard `*` is rejected at startup. |
| `UPLOAD_DIR` | `/app/uploads` | Directory for uploaded product images. Writable by `appuser` in Docker. |
| `ENVIRONMENT` | `development` | Runtime environment (`development` / `staging` / `production`). |
| `LOG_LEVEL` | `info` | Logging level (`debug` / `info` / `warning` / `error`). |
| `FX_API_KEY` | *(empty)* | Optional paid-tier key for ExchangeRate-API. Free tier at `FX_LIVE_API_URL` works without it. |
| `FX_API_URL` | `https://api.example.com/fx` | Reserved for a future paid FX data provider. |
| `FX_LIVE_API_URL` | `https://open.er-api.com/v6/latest/USD` | Live USD/NGN rate source (free, no key required). |
| `FX_CACHE_TTL_HOURS` | `4` | How long to cache the live FX rate in the DB before re-fetching from the external API. |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic API key for AI Recommendations, Price Suggestions, and Quick Quote. Get one at [console.anthropic.com](https://console.anthropic.com). |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Override to route Anthropic API calls through a proxy (e.g. cliproxy). Leave as default for direct access. |
| `POS_USERNAME` | *(empty)* | UltimatePOS login username. Only required when running `pos_migrate.py` — not used by the app at runtime. |
| `POS_PASSWORD` | *(empty)* | UltimatePOS login password. Only required when running `pos_migrate.py` — not used by the app at runtime. |

See `.env.example` for a fully annotated template and `.env.staging.example` for the staging/CI variable list.

---

## Testing

### Backend (pytest)
```bash
cd backend
UPLOAD_DIR=/tmp/modishlog_uploads .venv/bin/pytest tests/ -v
# Or inside Docker:
docker compose exec backend pytest tests/
```
849 tests covering all services, endpoints, and business logic.

### Frontend E2E (Playwright)
```bash
cd frontend
npx playwright test --reporter=list
```
E2E tests across auth, dashboard, products, sales, orders, FX, cashflow, and more.

### Frontend Build
```bash
cd frontend
npx ng build   # 0 errors, 0 warnings
```

---

## Architecture Decisions

- **All financial values use Python `Decimal`** mapped to `NUMERIC(18,6)` in PostgreSQL. Never use float for money.
- **Async everywhere** -- all database operations use SQLAlchemy async sessions with `await`.
- **FIFO inventory costing** -- sales are matched against oldest batches first for accurate COGS calculation.
- **Static routes before parameterized** -- FastAPI routers register `/summary`, `/batches` etc. before `/{id}` to avoid route conflicts.
- **Enum values_callable** -- new SQLAlchemy enum columns use `values_callable=lambda x: [e.value for e in x]` to ensure PostgreSQL enum values match Python enum values.
- **Eager loading** -- all relationships are loaded with `selectinload()` before returning ORM objects for Pydantic serialization.
- **Structured logging** -- uses `structlog` throughout; never `print()`.
- **TDD enforced** -- tests written before implementation. Every function has at least 2 tests (happy path + error case).
- **Lazy ML imports** -- heavy libraries (Prophet/Stan) are imported inside the functions that use them, not at module level. This keeps app startup time under 2 s and avoids OOM on containers with limited memory (e.g. 0.5 Gi).
- **SSL via connect_args** -- asyncpg does not accept `sslmode` as a URL query param. SSL is enabled by passing `connect_args={"ssl": True}` to `create_async_engine` and `async_engine_from_config` (alembic). The raw `DATABASE_URL` is normalised at startup: libpq params are stripped, and `DATABASE_SSL` is auto-derived from the original `sslmode` value.
- **HttpOnly cookie JWT** — access tokens are set as HttpOnly, SameSite=Lax cookies. The auth interceptor reads the cookie transparently; `localStorage` is never used for tokens. This eliminates XSS token theft.
- **Self-hosted fonts** — Inter is served via `@fontsource/inter` (bundled in the Angular build). No external font CDN requests; satisfies the Content-Security-Policy `default-src 'self'` rule.
- **Content-Security-Policy** — nginx serves `default-src 'self'` with narrowed directives for scripts, styles, images, and connections. `frame-ancestors 'none'` replaces the legacy `X-Frame-Options: DENY` header.
- **PrimeNG v21 dialog footer** — PrimeNG v21 removed the `pTemplate="footer"` string-keyed template API. Dialog footers must use the `#footer` local reference syntax instead. Any dialog missing this will render with no footer buttons.

---

## Security

The following hardening was applied after the initial build (PRs #95–#113):

| Area | Measure |
|------|---------|
| Auth tokens | JWT moved to HttpOnly, SameSite=Lax cookie — eliminates XSS token theft |
| API keys | Anthropic API key stored AES-encrypted in the database, not in `localStorage` |
| Registration | New-user registration requires admin auth — no open self-sign-up |
| JWT algorithm | Pinned to HS256/384/512 via startup validator — prevents `alg:none` attacks |
| Secret key | `SECRET_KEY` startup validation — server refuses to start without a real key |
| Password reset | Reset tokens SHA-256 hashed before DB storage — raw tokens never persisted |
| CORS | Explicit `allow_headers` list; wildcard-origin guard added |
| CSP | `Content-Security-Policy: default-src 'self'` served by nginx |
| Fonts | Inter self-hosted via `@fontsource/inter` — no external CDN in CSP |
| CSV exports | Formula injection (`=`, `+`, `-`, `@` prefixes) stripped before download |
| IDOR | Ownership checks on all individual-resource endpoints |
| Route auth | Auth dependency on every financial-data router (~50 routes) |
| Inventory | `SELECT FOR UPDATE` row lock in `adjust_stock` prevents oversell race |
| Error responses | Global exception handler — stack traces never leak in 500 responses |
| Products | `is_active` removed from `ProductUpdate` — prevents mass-assignment toggle |
| Products | `unit_cost` and `selling_price` validated `gt=0` — prevents division-by-zero |
| Orders | `DELIVERED` removed from editable statuses — prevents retroactive cost manipulation |

---

## Contributing

### Git Workflow
```
Branch:  feat/<task-id>-<description>
Commit:  feat(<domain>): <present-tense description>
```

1. Create branch from `main`
2. Write tests first (TDD)
3. Implement feature
4. Run `pytest` (all pass) + `ng build` (0 errors) + `ruff check`
5. Commit, push, open PR
6. Run `/review` agent on the PR
7. Merge after review

### Code Style
- Backend: `ruff check` + `ruff format`
- Frontend: Prettier
- Angular: standalone components, OnPush change detection, Signals

---

## License

Private / Proprietary. See LICENSE file for details.
