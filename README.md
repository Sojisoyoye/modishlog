# ModishLog

**AI-Powered Import & Trade Intelligence Platform**

A smart financial co-pilot for importers navigating currency volatility. ModishLog unifies FX forecasting, demand modelling, inventory management, cashflow monitoring, and AI-driven recommendations into a single platform.

---

## Features

### Core Platform
- **Authentication** -- JWT-based auth with role-based access (Admin / Sales Manager), account lockout with countdown timer, forgot password flow
- **Products** -- Full CRUD with categories, SKU auto-generation, image upload, search/filter, grid/list views, CSV export
- **Sales** -- Daily entry with stock validation, CSV bulk upload, edit/delete with audit trail, FIFO cost tracking
- **Inventory** -- Stock levels, low-stock alerts, batch tracking (FIFO), editable thresholds, depletion forecast with confidence intervals, liquidation candidates
- **Orders** -- Full lifecycle pipeline (Pending > In Production > Shipping > Clearing > Delivered), FX rate capture at creation and delivery, inline product creation, logistics cost tracking

### Financial Intelligence
- **FX Exposure** -- Multi-currency tracking (NGN/USD + EUR/USD), locked/floating exposure per order, cross-rate derivation (EUR/NGN), 180-day forecast with Prophet + Monte Carlo, rate alerts with configurable thresholds
- **Cashflow** -- 6-month rolling projection, DSCR monitoring, cash runway calculation, liquidity alerts, stress scenarios (FX shock, demand drop, combined), payment calendar
- **Pricing** -- Portfolio margin analysis, per-product margins with target tracking, demand elasticity configuration, cross-subsidisation display, price-FX sensitivity playground with scenario save
- **Global Exposure** -- Multi-currency debt bridge (EUR/USD/NGN), debt-to-trade ratio, currency toggle across panels

### AI & Automation
- **AI Recommendations** -- Unified ranked actions across pricing, inventory, FX, cashflow, and orders with apply/dismiss workflow
- **Logistics Efficiency** -- Shipping + clearing cost as % of COGS, 90-day rolling average, threshold alerts
- **Triage Mode** -- Liquidity squeeze detection with payment calendar, shortfall alerts, ranked corrective actions (liquidate, delay payment, accelerate collection)
- **Quick Quote** -- FIFO-based minimum sell price calculator with configurable floor margin
- **Strategic Mix Planner** -- Target revenue split by product category, actual vs target comparison, drift alerts

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL |
| Frontend | Angular 21 (standalone components, Signals), TailwindCSS v4, PrimeNG v21 |
| AI/ML | Prophet, NumPy/SciPy (Monte Carlo), scikit-learn |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Testing | pytest (416 tests), Playwright (87 E2E tests) |
| Infra | Docker, Docker Compose, Azure Container Apps, Neon PostgreSQL, Vercel, GitHub Actions |

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
│   │   ├── orders/        # Purchase orders, pipeline, logistics
│   │   ├── fx/            # FX rates, exposure, forecasting, simulation
│   │   ├── cashflow/      # Projections, DSCR, triage, global exposure
│   │   ├── pricing/       # Margins, elasticity, mix targets, sensitivity
│   │   ├── ai_engine/     # Recommendations, USD strategy, reorder
│   │   └── core/          # Config, database, security, logging
│   ├── alembic/           # Database migrations
│   ├── tests/             # 398 pytest tests
│   └── requirements.txt
├── frontend/
│   ├── src/app/
│   │   ├── features/      # 11 page modules (dashboard, sales, products, etc.)
│   │   ├── layout/        # Shell, sidebar, topbar
│   │   ├── shared/        # Reusable components
│   │   └── core/          # Services, guards, interceptors
│   ├── e2e/               # 87 Playwright E2E tests
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

### Option 1: Docker Compose

```bash
# Start all services
docker compose up -d

# Run migrations
docker compose exec backend alembic upgrade head

# Access the app
# Frontend: http://localhost:4200
# Backend API: http://localhost:8000/docs
```

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

---

## Staging Deployment

Staging runs on Azure Container Apps (backend) + Vercel (frontend) + Neon PostgreSQL.

| Component | Service |
|-----------|---------|
| Backend | Azure Container Apps (`modishlog-backend-staging`) |
| Database | Neon PostgreSQL (external, SSL required) |
| Migrations | Azure Container Apps Job (`modishlog-migrate-staging`) |
| Frontend | Vercel |
| Registry | GitHub Container Registry (GHCR) |
| CI/CD | GitHub Actions (`.github/workflows/deploy-staging.yml`) |

Every push to `main` triggers the pipeline:
1. Run `pytest` — must pass before deploy
2. Build Docker image → push to GHCR
3. Deploy frontend to Vercel
4. Update Container App image on Azure
5. Run Alembic migration job (`alembic upgrade head`)
6. Health-check `GET /health` until 200

**First-time setup:**
```bash
export STAGING_DATABASE_URL="postgresql://..."   # Neon connection string
export STAGING_SECRET_KEY="$(openssl rand -hex 32)"
export STAGING_CORS_ORIGINS="https://your-app.vercel.app"
export GHCR_TOKEN="ghp_..."
bash infra/azure/setup-staging.sh
```

Then add these GitHub Actions secrets to the repo:
`AZURE_CREDENTIALS`, `GHCR_TOKEN`, `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`

---

## API Documentation

Interactive API docs are available at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Key Endpoints

| Module | Endpoints |
|--------|-----------|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/forgot-password`, `POST /auth/reset-password` |
| Products | `GET/POST /products`, `PUT/DELETE /products/{id}`, `POST /products/{id}/image`, `GET/POST /products/categories` |
| Sales | `GET/POST /sales`, `PUT/DELETE /sales/{id}`, `POST /sales/upload`, `POST /sales/quick-quote`, `GET /sales/summary` |
| Inventory | `GET /inventory`, `POST /inventory/{id}/adjust`, `PUT /inventory/{id}/threshold`, `GET /inventory/batches`, `GET /inventory/batches/liquidation-candidates` |
| Orders | `GET/POST /orders`, `PUT /orders/{id}/status`, `GET /orders/logistics-efficiency`, `GET /orders/summary` |
| FX | `POST /fx/rates/ingest`, `GET /fx/rates/current`, `GET /fx/rates/{pair}/history`, `POST /fx/alerts`, `POST /fx/simulate`, `POST /fx/forecast/generate` |
| Cashflow | `GET /cashflow/projection`, `GET /cashflow/dscr`, `GET /cashflow/cash-runway`, `GET /cashflow/global-exposure`, `GET /cashflow/payment-calendar`, `GET /cashflow/triage-status`, `POST /cashflow/triage-check` |
| Pricing | `GET /pricing/portfolio-margin`, `GET /pricing/mix-status`, `POST /pricing/mix-targets`, `POST /pricing/sensitivity-calc`, `GET/POST /pricing/scenarios` |
| AI | `GET /ai/recommendations`, `POST /ai/recommendations/generate`, `POST /ai/recommendations/{id}/apply`, `POST /ai/recommendations/{id}/dismiss` |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://modishlog:modishlog_dev@localhost:5434/modishlog` | PostgreSQL connection string. Accepts `postgres://` / `postgresql://` — the app normalises to `postgresql+asyncpg://` and strips libpq params automatically. |
| `DATABASE_SSL` | *(auto-derived)* | Set to `true` to force SSL on the DB connection. Auto-set when the raw `DATABASE_URL` contains `sslmode=require` or `verify-*`. Required for Neon PostgreSQL in staging/production. |
| `SECRET_KEY` | `dev-secret-change-in-production` | JWT signing key |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT token lifetime in minutes |
| `UPLOAD_DIR` | `/uploads` | Directory for uploaded product images |
| `ENVIRONMENT` | `development` | Runtime environment (`development` / `staging` / `production`) |
| `LOG_LEVEL` | `info` | Logging level |
| `FX_API_KEY` | *(empty)* | External FX rate API key |
| `FX_API_URL` | `https://api.example.com/fx` | External FX rate API URL |
| `CORS_ORIGINS` | `["http://localhost:4200"]` | Allowed CORS origins (JSON array or comma-separated string) |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic API key for AI features |

---

## Testing

### Backend (pytest)
```bash
cd backend
UPLOAD_DIR=/tmp/modishlog_uploads .venv/bin/pytest tests/ -v
```
416 tests covering all services, endpoints, and business logic.

### Frontend E2E (Playwright)
```bash
cd frontend
npx playwright test --reporter=list
```
87 E2E tests across auth, dashboard, products, sales, orders, FX, and cashflow.

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
