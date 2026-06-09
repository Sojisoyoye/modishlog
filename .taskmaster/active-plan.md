# Task 16: Multi-Currency Debt Bridge (EUR/USD/NGN)

## Status: In Progress
## Complexity: 8/10

## Subtasks
- [ ] 16.1 — Database migration for loan obligations and EUR/USD support
- [ ] 16.2 — FX service extension for EUR/USD CRUD and cross-rate derivation
- [ ] 16.3 — Global exposure calculation service with debt-to-trade ratio
- [ ] 16.4 — Alert logic for EUR/USD threshold breaches
- [ ] 16.5 — Backend API endpoints for global exposure
- [ ] 16.6 — Frontend components for dashboard card, currency toggle, and widgets

## Key Files to Create/Modify

### Backend
- `backend/alembic/versions/` — New migration for loan_obligations columns
- `backend/src/cashflow/models.py` — Extend LoanObligation model
- `backend/src/cashflow/schemas.py` — Add GlobalExposure response schema
- `backend/src/cashflow/service.py` — Global exposure calculation logic
- `backend/src/cashflow/router.py` — GET /cashflow/global-exposure endpoint
- `backend/src/fx/models.py` — Ensure EUR/USD pair support
- `backend/src/fx/router.py` — POST /fx/rates for EUR/USD entries
- `backend/src/fx/service.py` — EUR/USD CRUD + cross-rate derivation
- `backend/tests/` — Tests for global exposure, EUR/USD CRUD, alert logic

### Frontend
- `frontend/src/app/features/dashboard/pages/dashboard-page.component.ts` — Add GlobalExposureCard
- `frontend/src/app/features/fx/pages/fx-page.component.ts` — EUR/USD rate input
- `frontend/src/app/core/services/cashflow.service.ts` — getGlobalExposure() method
- `frontend/src/app/core/services/fx.service.ts` — EUR/USD rate methods

## Approach
1. Start with migration + model changes (16.1)
2. Extend FX service for EUR/USD (16.2)
3. Build global exposure calculation (16.3)
4. Add alert logic (16.4)
5. Wire up API endpoints (16.5)
6. Frontend components (16.6)
7. Run pytest + ng build to verify

## Test Strategy
- pytest: global exposure calc with known rates, EUR/USD CRUD, alert threshold
- ng build: must compile with 0 errors
- All financial values use Python Decimal, never float
