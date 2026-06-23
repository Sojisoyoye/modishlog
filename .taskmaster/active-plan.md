# Active Plan — Task 126: Dashboard Overview Page — KPI Summary Cards

## Status: Awaiting Approval
## Complexity: 8/10

---

## 1. Task Summary

Add a KPI summary section to the existing `/dashboard` page
(`DashboardPageComponent`) showing 8 financial totals filterable by location
and date range, matching the screenshot: gradient welcome header, location
dropdown, date filter button, and 8 circle-icon KPI cards.

---

## 2. Critical Findings from Codebase Audit

### Models that EXIST and map to KPIs

| KPI | Model / Field | Scope |
|-----|--------------|-------|
| Total Sales | `Sale.total_amount` WHERE `status = COMPLETED` | `recorded_by = current_user.id` |
| NET | total_sales − SUM(`Sale.fifo_cogs`) − operating costs | same |
| Invoice Due | `Sale.total_amount` WHERE `payment_status != 'paid'` | same |
| Total Purchase | `PurchaseOrder.total_amount` | `created_by = current_user.id` |
| Purchase Due | `PurchaseOrder.total_amount` WHERE `payment_status = UNPAID` | same |
| Total Purchase Return | `PurchaseReturn.total_amount` (in `orders/models.py`) | via order `created_by` |

### Models that DO NOT EXIST yet — must be created in this task

| KPI | Missing | Plan |
|-----|---------|------|
| Total Sell Return / Sell Return Paid | No `SellReturn` table | Add `SellReturn` model to `sales/models.py` |
| Expense | No `Expense` table | Query `OperatingCost.monthly_equivalent WHERE is_active=True` for now; no new model needed |

### Other constraints discovered

- **No `business_id`** on User — isolation = `recorded_by / created_by = current_user.id`.
- **No `location_id` on `Sale`** — must add nullable FK via Alembic migration.
- **`location_id` does exist** on `PurchaseOrder` already.
- **Dashboard route already exists** at `path: 'dashboard'` in `app.routes.ts` →
  subtask 126.8 becomes "wire location dropdown" only, not new route registration.
- **`MetricCardComponent` already exists** (border-left pattern) — the new
  `KpiCardComponent` is a distinct circle-icon layout as per screenshot.
- **Existing `DashboardPageComponent`** already has Liquidity, FX Exposure, etc. cards.
  The KPI banner is **prepended at the top** of that component, not a new page.

---

## 3. Files to Create

| Path | Purpose |
|------|---------|
| `backend/src/dashboard/__init__.py` | New domain init |
| `backend/src/dashboard/schemas.py` | `DashboardSummaryResponse` (10 Decimal fields) |
| `backend/src/dashboard/service.py` | `get_dashboard_summary()` async aggregation |
| `backend/src/dashboard/router.py` | `GET /api/v1/dashboard/summary` |
| `backend/alembic/versions/<hash>_add_sell_return_and_sale_location.py` | Migration |
| `backend/tests/test_dashboard_summary.py` | 6 pytest cases |
| `frontend/src/app/features/dashboard/models/dashboard-kpi.model.ts` | `DashboardKpiSummary` interface |
| `frontend/src/app/features/dashboard/services/dashboard-kpi.service.ts` | `DashboardKpiService` |
| `frontend/src/app/shared/components/kpi-card/kpi-card.component.ts` | Reusable KPI card |
| `frontend/e2e/dashboard-kpi.spec.ts` | 8 Playwright E2E cases |

## 4. Files to Modify

| Path | Change |
|------|--------|
| `backend/src/sales/models.py` | Add nullable `location_id` FK to `Sale`; add `SellReturn` class |
| `backend/src/main.py` | Register `dashboard_router` under `/api/v1/dashboard` |
| `frontend/src/app/features/dashboard/pages/dashboard-page.component.ts` | Prepend KPI banner, inject `DashboardKpiService` + `LocationsService` |

---

## 5. Step-by-Step Approach

### Step 1 — Git branch
```
git checkout -b feat/126-dashboard-kpi-summary-cards
```

### Step 2 — 126.1: Write backend tests first (TDD)
Write `backend/tests/test_dashboard_summary.py` — all 6 cases. They FAIL
until the endpoint is built.

### Step 3 — 126.2: Schema + models + migration + service
- Add `SellReturn` model + nullable `location_id` to `Sale` in `sales/models.py`
- Generate Alembic migration
- Create `backend/src/dashboard/schemas.py` and `service.py`

### Step 4 — 126.3: Router + register
- Create `backend/src/dashboard/router.py`
- Register in `main.py` under `/api/v1/dashboard` (static prefix first)
- `docker compose exec backend pytest tests/test_dashboard_summary.py` → all green

### Step 5 — 126.4: Write E2E tests first (TDD)
Write `frontend/e2e/dashboard-kpi.spec.ts` — all 8 cases. They FAIL until
the component is built.

### Step 6 — 126.5: KpiCardComponent
- `frontend/src/app/shared/components/kpi-card/kpi-card.component.ts`
- Inputs: `label`, `value`, `iconClass`, `iconBgColor`, `subLines?`, `loading`

### Step 7 — 126.6: DashboardKpiService
- Interface + HttpClient service calling `/api/v1/dashboard/summary`

### Step 8 — 126.7: Expand DashboardPageComponent
- Gradient header + location p-dropdown + date p-calendar + 8 `KpiCardComponent`
  instances prepended above the existing cards

### Step 9 — 126.8: Wire location dropdown
- Inject `LocationsService.listLocations()` into component
- First option: `{label: 'All locations', value: null}`

### Step 10 — 126.9: Visual polish
- Exact colours, PrimeIcons, tooltip on NET, responsive grid breakpoints

### Step 11 — 126.10: Full gate + PR
- `pytest tests/` green → `ng build` green → Playwright green → open PR

---

## 6. TDD Test Plan

### Backend — `tests/test_dashboard_summary.py`

Fixture pattern from `tests/test_sales.py`: `_make_user()` factory,
mock async session via `AsyncMock`, `TestClient`, `build_token`.

```
test_summary_happy_path          — correct totals for seeded data
test_summary_location_filter     — totals change with location_id param
test_summary_date_filter         — only transactions in window counted
test_summary_empty_state         — all 10 fields = "0.00" with no data
test_summary_auth_guard          — no token → 401
test_summary_cross_user_isolation — user A cannot see user B data
```

### Frontend Playwright — `frontend/e2e/dashboard-kpi.spec.ts`

Uses `loginViaAPI()` from `./helpers/auth`. Pattern matches `dashboard.spec.ts`.

```
test 1 — "Welcome Soji," heading visible
test 2 — all 8 KPI card labels visible
test 3 — all values show ₦ 0.00 on empty account
test 4 — location dropdown renders
test 5 — selecting a location triggers re-fetch
test 6 — Filter by date button opens calendar
test 7 — Sell Return card shows both sub-lines
test 8 — Purchase Return card shows both sub-lines
```

---

## 7. Key Decisions

1. **KPI section prepended to existing `DashboardPageComponent`** — no new route.
2. **`location_id` (nullable) added to `Sale`** via migration — sales without a
   location are included in "All locations" queries.
3. **`SellReturn`** added to `sales/models.py`: fields `sale_id FK`, `return_date`,
   `total_amount Decimal`, `amount_paid Decimal`, `created_by FK`.
4. **Expense** sourced from `OperatingCost.monthly_equivalent WHERE is_active=True`
   filtered by `created_by` — avoids a new model for now.
5. **`KpiCardComponent`** is a new shared component (circle-icon layout) separate
   from the existing `MetricCardComponent` (border-left layout).

---

## 8. Estimated Token Budget

| Phase | ~tokens |
|-------|---------|
| Backend tests (126.1) | 8k |
| Schema + models + migration + service (126.2) | 14k |
| Router + register (126.3) | 4k |
| E2E tests (126.4) | 6k |
| KpiCardComponent (126.5) | 4k |
| DashboardKpiService (126.6) | 4k |
| DashboardPageComponent expansion (126.7) | 10k |
| Location dropdown (126.8) | 3k |
| Visual polish (126.9) | 5k |
| Gate + PR (126.10) | 3k |
| **Total** | **~61k** |

---

## AWAITING APPROVAL — type "Plan approved" to begin with subtask 126.1
