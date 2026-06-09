# ModishLog QA Test Report

**Date:** 2026-04-11
**Tester:** Claude Code (QA + UI/UX)
**Environment:** macOS, Python 3.11, Angular 21, PostgreSQL 16, localhost

---

## CRITICAL BUGS (P0 - Blocks Usage)

### BUG-001: User registration fails with 500 — enum case mismatch
- **Endpoint:** `POST /api/v1/auth/register`
- **Error:** `asyncpg.exceptions.InvalidTextRepresentationError: invalid input value for enum userrole: "ADMIN"`
- **Root cause:** PostgreSQL enum `userrole` was created with lowercase values (`admin`, `sales_manager`) but SQLAlchemy sends uppercase `ADMIN` when setting `role=UserRole.ADMIN` in `create_user`. The Python enum has `.value = "admin"` but the ORM is sending the enum name instead of value.
- **Impact:** No users can be registered. The entire application is unusable.
- **Fix:** Ensure SQLAlchemy uses `.value` for enum insertion, or align the PostgreSQL enum values with Python enum names.

### BUG-002: Alembic migration chain had duplicate revision IDs
- **Files:** `d4e5f6a7b8c9_add_triage_records_table.py` and `d4e5f6a7b8c9_add_product_mix_targets_table.py`
- **Error:** `Multiple head revisions are present` — migrations could not run
- **Root cause:** Tasks 19 and 21 were implemented on separate branches and both agents independently chose the same revision ID pattern. The mix targets migration also pointed to the wrong `down_revision`.
- **Impact:** Database cannot be migrated from scratch. Production deploy would fail.
- **Status:** Fixed during QA — renamed mix targets to `d5e6f7a8b9c0`, fixed chain.
- **Recommendation:** Use `alembic revision --autogenerate` or random UUIDs for revision IDs instead of hand-crafted sequential hex patterns.

### BUG-003: Products endpoint returns 500 on listing
- **Endpoint:** `GET /api/v1/products`
- **Error:** 500 Internal Server Error (no auth required but still fails)
- **Likely cause:** The `list_products` service may have a query issue or the products table schema doesn't match the model (possibly related to the unmerged products page changes from task 14).
- **Impact:** Products cannot be listed, which blocks all downstream features (sales, inventory, orders).

---

## HIGH BUGS (P1 - Major Feature Broken)

### BUG-004: Route conflict — `/orders/logistics-efficiency` parsed as `/{order_id}`
- **Endpoint:** `GET /api/v1/orders/logistics-efficiency`
- **Error:** `422 Unprocessable Entity` — `"Input should be a valid UUID... found 'l' at 1"`
- **Root cause:** FastAPI route ordering. The `/{order_id}` path parameter route matches before `/logistics-efficiency`. The logistics endpoint is defined after the parameterized route.
- **Impact:** Logistics efficiency endpoint is inaccessible.
- **Fix:** Move `/logistics-efficiency` route BEFORE `/{order_id}` in `orders/router.py`, or use a more specific path like `/reports/logistics-efficiency`.

### BUG-005: Route conflict — `/inventory/batches` parsed as `/{product_id}`
- **Endpoint:** `GET /api/v1/inventory/batches?product_id=X`
- **Error:** Same 422 UUID parsing error
- **Root cause:** Same route ordering issue as BUG-004. `/batches` is matched by `/{product_id}`.
- **Impact:** Batch endpoints are inaccessible.
- **Fix:** Move batch routes before parameterized routes, or use `/inventory/batch-list` etc.

### BUG-006: Triage status endpoint returns 500
- **Endpoint:** `GET /api/v1/cashflow/triage-status`
- **Error:** 500 Internal Server Error
- **Likely cause:** The endpoint returns `None` directly when no triage is active, but FastAPI may not handle a `None` return for a response_model of `TriageStatusResponse | None` correctly, or there's a serialization issue.
- **Impact:** Dashboard triage banner cannot check triage state.

---

## MEDIUM BUGS (P2 - Feature Degraded)

### BUG-007: Frontend products page doesn't compile
- **File:** `frontend/src/app/features/products/pages/products-page.component.ts`
- **Errors:** 30+ TypeScript errors — missing exports (`Category`, `ProductCreate`, `ProductUpdate`, `create`, `update`, `delete`, `getCategories`, `uploadImage`) from `products.service.ts`
- **Root cause:** The products page was built against an older version of the service (from task 14 working tree) but `products.service.ts` on main doesn't have these methods/interfaces. The service was merged with CRUD methods but the page references interfaces not exported.
- **Impact:** Frontend cannot build with the products page included. Currently works only by excluding the products directory.
- **Fix:** Align products.service.ts exports with what products-page.component.ts imports, or merge the uncommitted products service changes.

### BUG-008: FX service `addManualRate` hardcodes pair to USDNGN on main
- **File:** `frontend/src/app/core/services/fx.service.ts`
- **Note:** The task 16 changes added EUR/USD support via `data.rate_type` parameter, but this was merged. On main the service should have the pair-aware version. Verify after rebuild.

### BUG-009: `test_create_product_without_category` pre-existing failure
- **Test:** `tests/test_products.py::TestProductCRUD::test_create_product_without_category`
- **Error:** `pydantic_core._pydantic_core.ValidationError: category_id Field required`
- **Root cause:** The `ProductCreate` schema has `category_id: uuid.UUID | None = None` but the test creates without it and the validation fails. This suggests the schema on the working tree differs from what's in git.
- **Impact:** CI test suite has 1 persistent failure.

---

## LOW BUGS (P3 - Minor / Cosmetic)

### BUG-010: Pydantic `model_version` namespace warning on startup
- **Warning:** `Field "model_version" has conflict with protected namespace "model_"`
- **File:** `src/fx/models.py` — `FXForecast.model_version`
- **Fix:** Add `model_config = ConfigDict(protected_namespaces=())` to the model, or rename the field.

### BUG-011: `plotly` import warning on startup
- **Warning:** `Importing plotly failed. Interactive plots will not work.`
- **Fix:** Either install plotly or suppress the warning if it's not needed.

### BUG-012: Frontend bundle size warning
- **Warning:** `bundle initial exceeded maximum budget. Budget 500.00 kB was not met by ~5.8 kB`
- **Impact:** Cosmetic CI warning, no functional impact.
- **Fix:** Increase budget in angular.json or optimize imports.

---

## ROUTE/API ISSUES

### ISSUE-001: Inconsistent API response format
- `GET /fx/rates/current` returns `[]` (empty array) — OK
- `GET /cashflow/dscr` returns object — OK
- `GET /cashflow/triage-status` returns 500 instead of null — NOT OK
- Some endpoints require auth, some don't — inconsistent

### ISSUE-002: No OpenAPI docs customization
- `/docs` (Swagger UI) works but has no grouped tags or descriptions beyond auto-generated ones.
- Recommendation: Add `tags_metadata` to the FastAPI app for better API documentation.

---

## UI/UX OBSERVATIONS

### UX-001: Cannot test frontend end-to-end
- Backend registration is broken (BUG-001), so login flow cannot be tested
- Products page doesn't compile (BUG-007)
- These block all UI testing

### UX-002: Dashboard cards have good visual design
- From code review: the dashboard template has well-structured cards with proper Tailwind styling
- GlobalExposureCard, LogisticsEfficiencyCard, TriageBanner all follow consistent design patterns
- Color coding (success/warning/danger) is applied consistently

### UX-003: No loading states on new dashboard cards
- The GlobalExposure, Logistics, and Triage cards show nothing while loading (vs the main dashboard which shows skeleton loaders)
- Recommendation: Add skeleton loaders or loading spinners for these cards

### UX-004: Currency toggle only on GlobalExposureCard
- The PRD specifies "Currency toggle (EUR / USD / NGN) on all financial summary panels"
- Currently only implemented on the GlobalExposureCard, not on other panels
- Recommendation: Add currency toggle to Liquidity, FX Exposure, and Portfolio Margin cards

---

## SECURITY OBSERVATIONS

### SEC-001: Image upload validation added (Good)
- Extension whitelist (.jpg/.jpeg/.png/.webp) and 5MB size limit — implemented in PR #1 review fixes

### SEC-002: JWT tokens have no refresh mechanism
- Tokens expire but there's no refresh token flow
- Users must re-login after expiry

### SEC-003: CORS allows all origins in development
- `settings.CORS_ORIGINS` — verify this is restricted in production

---

## TEST COVERAGE SUMMARY

| Area | Tests | Status |
|------|-------|--------|
| Auth | 21 | Pass (except BUG-009) |
| Products + Inventory | 23 | Pass |
| Sales | 20 | Pass |
| Orders | 17 | Pass |
| FX | 27 | Pass |
| Cashflow | 24 | Pass |
| Pricing | 20 | Pass |
| AI Engine | 43 | Pass |
| FIFO (Task 18) | 12 | Pass |
| Global Exposure (Task 16) | 11 | Pass |
| Logistics (Task 17) | 12 | Pass |
| Triage (Task 21) | 12 | Pass |
| Quick Quote (Task 22) | 4 | Pass |
| Sensitivity (Task 20) | 10 | Pass |
| Mix Planner (Task 19) | 8 | Pass |
| **Total** | **~385** | **384 pass, 1 fail** |

---

## PRIORITY ACTION ITEMS

1. **P0:** Fix BUG-001 (user registration enum) — blocks all usage
2. **P0:** Fix BUG-003 (products 500 error) — investigate root cause
3. **P1:** Fix BUG-004 and BUG-005 (route ordering) — move static routes before parameterized
4. **P1:** Fix BUG-006 (triage status 500) — handle None return properly
5. **P2:** Fix BUG-007 (products page TypeScript errors) — align service with component
6. **P2:** Commit migration chain fix (already done locally, needs push)
7. **P3:** Address BUG-009, BUG-010, BUG-011, BUG-012
