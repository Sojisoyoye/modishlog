# Active Plan — Dashboard Hero Section Redesign (ad-hoc, 2026-06-30)

> Supersedes the old Task 126 plan below.  New work starts here.

---

## Summary

Replace the dark slate gradient banner + 8-KPI-card top row in `DashboardPageComponent`
with an emerald hero card row (Today's Revenue | Gross Margin | Sales Today) plus a
Recent Sales table. The existing filters, KPI cards, and all lower rows are kept — just
moved below the new hero section.

Backend must expose 3 new fields on `GET /api/v1/dashboard/summary`:
- `transaction_count` — count of completed sales in the filtered window
- `yesterday_sales` — serialized Decimal sum of yesterday's completed sales
- `recent_sales` — list of last 5 completed sales (joined with Product for name)

---

## Files to Modify

### Backend
| File | Action |
|------|--------|
| `backend/src/dashboard/schemas.py` | Add `RecentSaleItem`; add 3 new fields to `DashboardSummaryResponse`; extend `@field_serializer` for `yesterday_sales` |
| `backend/tests/test_dashboard_summary.py` | Add Test A + Test B at the end (TDD first) |
| `backend/src/dashboard/service.py` | Add 3 queries (`q_count`, `q_yesterday`, `q_recent`) + result assembly |

### Frontend
| File | Action |
|------|--------|
| `frontend/src/app/features/dashboard/models/dashboard-kpi.model.ts` | Add `RecentSaleItem` interface + 3 new fields on `DashboardKpiSummary` |
| `frontend/src/app/features/dashboard/pages/dashboard-page.component.ts` | Replace lines 36–96; add 4 computed helpers; keep all rows below |

---

## Step-by-Step Approach

### Step 1 — Backend Schema (no behaviour yet)

**File:** `backend/src/dashboard/schemas.py`

Add `RecentSaleItem` before `DashboardSummaryResponse`:
```python
class RecentSaleItem(BaseModel):
    product_name: str
    quantity: int
    revenue: str       # serialized Decimal string
    margin_pct: str | None

    model_config = {"from_attributes": True}
```

Add to `DashboardSummaryResponse` (keep all 10 existing fields):
```python
transaction_count: int = 0
yesterday_sales: Decimal = Decimal("0")
recent_sales: list[RecentSaleItem] = Field(default_factory=list)
```

Extend `@field_serializer` to add `"yesterday_sales"` to the field list.

> Using `Field(default=...)` on new fields ensures existing tests that call
> `DashboardSummaryResponse(total_sales=..., ...)` without the new args still work.

---

### Step 2 — Write Tests FIRST (TDD)

**File:** `backend/tests/test_dashboard_summary.py`

Update `_make_summary()` to pass `transaction_count=0`, `yesterday_sales=Decimal("0.00")`, `recent_sales=[]` as defaults (so Tests 1–6 still pass).

Append at end of file:

**Test A — happy path with new fields**
```python
def test_summary_new_fields_happy_path():
    """transaction_count, yesterday_sales and recent_sales returned correctly."""
    from src.dashboard.schemas import DashboardSummaryResponse, RecentSaleItem
    from src.main import app

    user = _make_user()
    summary = _make_summary(
        transaction_count=5,
        yesterday_sales=Decimal("800.00"),
        recent_sales=[
            RecentSaleItem(
                product_name="Test Product",
                quantity=2,
                revenue="500.00",
                margin_pct="30.00",
            )
        ],
    )
    app_inst, _, orig = _setup_app(user)
    try:
        import src.dashboard.router as dash_router
        original = dash_router.get_dashboard_summary
        dash_router.get_dashboard_summary = AsyncMock(return_value=summary)
        with TestClient(app_inst) as client:
            resp = client.get("/api/v1/dashboard/summary", headers=_auth_headers(user))
    finally:
        dash_router.get_dashboard_summary = original
        _teardown_app(app_inst, orig)

    assert resp.status_code == 200
    data = resp.json()
    assert data["transaction_count"] == 5
    assert data["yesterday_sales"] == "800.00"
    assert len(data["recent_sales"]) == 1
    assert data["recent_sales"][0]["product_name"] == "Test Product"
    assert data["recent_sales"][0]["quantity"] == 2
    assert data["recent_sales"][0]["revenue"] == "500.00"
    assert data["recent_sales"][0]["margin_pct"] == "30.00"
```

**Test B — zero state**
```python
def test_summary_zero_state_new_fields():
    """transaction_count=0 and recent_sales=[] serialized correctly."""
    from src.main import app

    user = _make_user()
    summary = _make_summary(
        transaction_count=0,
        yesterday_sales=Decimal("0.00"),
        recent_sales=[],
    )
    app_inst, _, orig = _setup_app(user)
    try:
        import src.dashboard.router as dash_router
        original = dash_router.get_dashboard_summary
        dash_router.get_dashboard_summary = AsyncMock(return_value=summary)
        with TestClient(app_inst) as client:
            resp = client.get("/api/v1/dashboard/summary", headers=_auth_headers(user))
    finally:
        dash_router.get_dashboard_summary = original
        _teardown_app(app_inst, orig)

    assert resp.status_code == 200
    data = resp.json()
    assert data["transaction_count"] == 0
    assert data["yesterday_sales"] == "0.00"
    assert data["recent_sales"] == []
```

---

### Step 3 — Backend Service Implementation

**File:** `backend/src/dashboard/service.py`

Add `timedelta` to the existing `from datetime import date` import.
Add `from src.products.models import Product` import.

After the 8 existing query definitions, add:

```python
# -- Query 9: transaction_count
q_count = select(func.count(Sale.id)).where(
    Sale.recorded_by == user_id,
    Sale.status == SaleStatus.COMPLETED,
)
if location_id is not None:
    q_count = q_count.where(Sale.location_id == location_id)
if date_from is not None:
    q_count = q_count.where(Sale.sale_date >= date_from)
if date_to is not None:
    q_count = q_count.where(Sale.sale_date <= date_to)

# -- Query 10: yesterday_sales
from datetime import timedelta
yesterday = date.today() - timedelta(days=1)
q_yesterday = select(func.coalesce(func.sum(Sale.total_amount), _ZERO)).where(
    Sale.recorded_by == user_id,
    Sale.status == SaleStatus.COMPLETED,
    Sale.sale_date == yesterday,
)
if location_id is not None:
    q_yesterday = q_yesterday.where(Sale.location_id == location_id)

# -- Query 11: recent_sales (last 5)
from src.products.models import Product as _Product
q_recent = (
    select(_Product.name, Sale.quantity, Sale.total_amount, Sale.fifo_cogs)
    .join(_Product, Sale.product_id == _Product.id)
    .where(
        Sale.recorded_by == user_id,
        Sale.status == SaleStatus.COMPLETED,
    )
    .order_by(Sale.created_at.desc())
    .limit(5)
)
if location_id is not None:
    q_recent = q_recent.where(Sale.location_id == location_id)
if date_from is not None:
    q_recent = q_recent.where(Sale.sale_date >= date_from)
if date_to is not None:
    q_recent = q_recent.where(Sale.sale_date <= date_to)
```

After the existing `await db.execute(...)` calls:
```python
r_count    = await db.execute(q_count)
r_yesterday = await db.execute(q_yesterday)
r_recent   = await db.execute(q_recent)
```

Extract and build:
```python
transaction_count: int = r_count.scalar_one()
yesterday_sales: Decimal = r_yesterday.scalar_one()

def _margin(revenue: Decimal, cogs: Decimal | None) -> str | None:
    if cogs is None or revenue == _ZERO:
        return None
    return f"{((revenue - cogs) / revenue * 100):.1f}"

from src.dashboard.schemas import RecentSaleItem
recent_sales = [
    RecentSaleItem(
        product_name=row[0],
        quantity=row[1],
        revenue=f"{row[2]:.2f}",
        margin_pct=_margin(row[2], row[3]),
    )
    for row in r_recent.all()
]
```

Update return statement:
```python
return DashboardSummaryResponse(
    ...,  # all 10 existing fields
    transaction_count=transaction_count,
    yesterday_sales=yesterday_sales,
    recent_sales=recent_sales,
)
```

---

### Step 4 — Run Backend Tests

```bash
docker compose exec backend pytest tests/test_dashboard_summary.py -x -q
```

All 8 tests must pass before proceeding.

---

### Step 5 — Frontend Model

**File:** `frontend/src/app/features/dashboard/models/dashboard-kpi.model.ts`

```typescript
export interface RecentSaleItem {
  product_name: string;
  quantity: number;
  revenue: string;
  margin_pct: string | null;
}

export interface DashboardKpiSummary {
  // ... existing 10 fields ...
  transaction_count: number;
  yesterday_sales: string;
  recent_sales: RecentSaleItem[];
}
```

---

### Step 6 — Frontend Template Replacement

Replace lines 36–96 in `dashboard-page.component.ts` template with:

```html
<div class="space-y-5">

  <!-- Hero row -->
  <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
    <!-- Today's Revenue — emerald -->
    <div class="flex flex-col justify-between rounded-2xl bg-emerald-600 p-6 text-white shadow-sm">
      <div>
        <p class="text-sm font-medium text-emerald-100">Today's Revenue</p>
        <p class="mt-2 text-4xl font-bold tracking-tight">
          @if (kpiLoading()) {
            <span class="inline-block h-10 w-32 animate-pulse rounded bg-emerald-500"></span>
          } @else {
            ₦{{ kpi()?.total_sales ?? '0.00' | number: '1.0-0' }}
          }
        </p>
      </div>
      <p class="mt-4 flex items-center gap-1.5 text-sm font-medium" [class]="revenueChangeClass()">
        <i [class]="revenueChangeIcon()"></i>
        {{ revenueChangePct() }}% vs yesterday
      </p>
    </div>

    <!-- Gross Margin -->
    <div class="flex flex-col justify-between rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
      <div>
        <p class="text-sm font-medium text-muted">Gross Margin</p>
        <p class="mt-2 text-4xl font-bold tracking-tight text-gray-900">
          @if (loading()) {
            <span class="inline-block h-10 w-24 animate-pulse rounded bg-gray-100"></span>
          } @else {
            {{ data().profitMargin.blended_margin | number: '1.1-1' }}%
          }
        </p>
      </div>
      <p class="mt-4 flex items-center gap-1.5 text-sm font-medium" [class]="marginGapColor()">
        <i [class]="data().profitMargin.margin_gap >= 0 ? 'pi pi-arrow-up text-xs' : 'pi pi-arrow-down text-xs'"></i>
        {{ data().profitMargin.margin_gap >= 0 ? 'On target' : (data().profitMargin.margin_gap | number: '1.1-1') + '% vs target' }}
      </p>
    </div>

    <!-- Sales Today -->
    <div class="flex flex-col justify-between rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
      <div>
        <p class="text-sm font-medium text-muted">Sales Today</p>
        <p class="mt-2 text-4xl font-bold tracking-tight text-gray-900">
          @if (kpiLoading()) {
            <span class="inline-block h-10 w-16 animate-pulse rounded bg-gray-100"></span>
          } @else {
            {{ kpi()?.transaction_count ?? 0 }}
          }
        </p>
      </div>
      <p class="mt-4 text-sm text-muted">transactions</p>
    </div>
  </div>

  <!-- Recent Sales table -->
  <div class="rounded-2xl border border-gray-100 bg-white shadow-sm">
    <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
      <h2 class="text-base font-semibold text-gray-900">Recent Sales</h2>
      <a routerLink="/sales" class="text-xs font-semibold text-emerald-600 hover:text-emerald-700">
        View all <i class="pi pi-arrow-right text-[10px]"></i>
      </a>
    </div>
    @if (kpiLoading()) {
      <div class="px-6 py-8 text-center text-sm text-muted">Loading…</div>
    } @else if (!kpi()?.recent_sales?.length) {
      <div class="px-6 py-8 text-center text-sm text-muted">No sales recorded today yet.</div>
    } @else {
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-gray-100">
            <th class="px-6 py-3 text-left text-xs font-semibold uppercase text-muted">Product</th>
            <th class="px-6 py-3 text-right text-xs font-semibold uppercase text-muted">Qty</th>
            <th class="px-6 py-3 text-right text-xs font-semibold uppercase text-muted">Revenue</th>
            <th class="px-6 py-3 text-right text-xs font-semibold uppercase text-muted">Margin</th>
          </tr>
        </thead>
        <tbody>
          @for (sale of kpi()!.recent_sales; track sale.product_name) {
            <tr class="border-b border-gray-50 last:border-0">
              <td class="px-6 py-3 font-medium text-gray-900">{{ sale.product_name }}</td>
              <td class="px-6 py-3 text-right text-muted">{{ sale.quantity }}</td>
              <td class="px-6 py-3 text-right text-gray-900">₦{{ sale.revenue | number: '1.0-0' }}</td>
              <td class="px-6 py-3 text-right font-semibold" [class]="marginClass(sale.margin_pct)">
                {{ sale.margin_pct !== null ? sale.margin_pct + '%' : '—' }}
              </td>
            </tr>
          }
        </tbody>
      </table>
    }
  </div>

  <!-- Filters row (powers KPI cards below) -->
  <div class="flex flex-wrap items-center gap-3 rounded-xl border border-gray-100 bg-white px-4 py-3 shadow-sm">
    <span class="text-sm font-medium text-muted">Filter:</span>
    <!-- p-select and p-datepicker — exact markup from old dark banner, keep unchanged -->
    ...
  </div>

  <!-- 8 KPI cards (identical, just moved below) -->
  <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
    ...
  </div>
  <!-- rest of template unchanged from line 98 onward -->
```

Key change: The `userName()` greeting and the `liveRate()` chip from the old
dark banner are removed (not in new spec). The `liveRate` and `userName` signals
stay in the class to avoid subscription leaks; they just aren't referenced in
the template (TypeScript won't error on unused signals).

---

### Step 7 — Add Computed Helpers to Class

Add after the existing `purchaseReturnSubLines` computed:

```typescript
revenueChangePct = computed(() => {
  const today = parseFloat(this.kpi()?.total_sales ?? '0');
  const yesterday = parseFloat(this.kpi()?.yesterday_sales ?? '0');
  if (yesterday === 0) return 0;
  return Math.abs(Math.round(((today - yesterday) / yesterday) * 100));
});

revenueChangeClass = computed(() => {
  const today = parseFloat(this.kpi()?.total_sales ?? '0');
  const yesterday = parseFloat(this.kpi()?.yesterday_sales ?? '0');
  return today >= yesterday ? 'text-emerald-200' : 'text-red-200';
});

revenueChangeIcon = computed(() => {
  const today = parseFloat(this.kpi()?.total_sales ?? '0');
  const yesterday = parseFloat(this.kpi()?.yesterday_sales ?? '0');
  return today >= yesterday ? 'pi pi-arrow-up text-xs' : 'pi pi-arrow-down text-xs';
});

marginClass(pct: string | null): string {
  if (pct === null) return 'text-muted';
  const n = parseFloat(pct);
  return n >= 30 ? 'text-emerald-600' : n >= 15 ? 'text-amber-600' : 'text-red-500';
}
```

Import `RecentSaleItem` is not needed in the component — it comes via the template only.

---

### Step 8 — Frontend Build Verification

```bash
cd /Users/sojisoyoye/workspace/modishlog/frontend && ng build --configuration production 2>&1 | tail -20
```

Zero errors required before committing.

---

## TDD Plan

### Backend (write BEFORE service.py changes)
| Test | Fields verified |
|------|----------------|
| Test A (new) | `transaction_count=5`, `yesterday_sales="800.00"`, `recent_sales[0].product_name` |
| Test B (new) | `transaction_count=0`, `recent_sales=[]` |
| Tests 1–6 (existing) | All must still pass — guaranteed by schema defaults |

### Frontend (Playwright — deferred)
Playwright E2E test coverage for dashboard hero is a follow-up task. Compile-time
verification via `ng build` is the gate for this task.

---

## Watch-outs

1. `DashboardSummaryResponse` new fields need Python `Field(default=...)` so existing
   tests that call `_make_summary()` without the new kwargs don't break.
2. `yesterday_sales` must be in the `@field_serializer` decorator list — it's a `Decimal`
   and would otherwise be serialized as a float by Pydantic.
3. Angular `number` pipe on a `string` value (e.g. `sale.revenue`) — the pipe will
   coerce it via `parseFloat` internally, which works. Tested at build time.
4. `[class]="expr"` — must be a string expression; all 4 helpers return strings.
5. `timedelta` import: `from datetime import date` already exists; add `, timedelta`.
6. `Product` import in service: must avoid name clash — alias as `_Product` or check
   if `Product` is already imported (it is not in the current service.py).

---

## Estimated Token Budget

| Phase | Est. tokens |
|-------|-------------|
| Schema edit | ~400 |
| Test authoring (2 tests) | ~800 |
| Service edit | ~1,200 |
| Frontend model | ~300 |
| Template replacement | ~2,500 |
| Class helpers | ~400 |
| Build verification | ~300 |
| **Total** | **~6,000** |

---

## Blockers

None. All models (`Sale`, `Product`, `SaleStatus`) are importable. Backend is additive
(new fields with defaults). Frontend changes are isolated to 2 files.

---

---

# OLD PLAN (Task 126 — archived)

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
