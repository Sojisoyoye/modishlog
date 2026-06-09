# ModishLog Frontend UI Audit Report

**Date:** 2026-04-10
**Scope:** All Angular page-level components audited against PRD acceptance criteria
**Files audited:** 10 page components, 1 sidebar, 1 shell, 4 shared components

---

## CRITICAL / BLOCKING ISSUES

### 1. Products page has NO route and NO sidebar navigation entry
- `app.routes.ts` has no `path: 'products'` route
- `sidebar.component.ts` nav items list has 8 entries -- Dashboard, Sales, Inventory, Orders, Pricing, FX Rates, Cashflow, AI Insights -- but **no "Products" link**
- The Products page component exists at `frontend/src/app/features/products/pages/products-page.component.ts` but is completely unreachable in the app
- **Impact:** Users cannot navigate to the Products management page at all

### 2. Sidebar has only 8 nav items instead of the 9 implied by PRD Section 5.8
- Missing: Products
- Present: Dashboard, Sales, Inventory, Orders, Pricing, FX Rates, Cashflow, AI Insights

---

## PER-COMPONENT AUDIT

---

### 1. LOGIN PAGE
**File:** `frontend/src/app/features/auth/pages/login-page.component.ts`
**PRD Reference:** ST-101 -- Secure Login

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | Login screen first for unauthenticated users | PASS | `authGuard` on all routes redirects to `/login`; login route is unguarded |
| 2 | Error display on failed attempts | PASS | `errorMessage()` signal shown in red banner; 401 -> "Invalid email or password" |
| 3 | Loading state during login | PASS | `loading()` signal disables button, shows spinner + "Signing in..." |
| 4 | 15-minute lockout with visible countdown | PARTIAL | 429 response triggers "Account locked for 15 minutes" message, but **no countdown timer** is displayed |
| 5 | "Forgot password" flow | MISSING | No "Forgot password" link anywhere in the template |
| 6 | Form validation (email format, min length) | PARTIAL | `required` and `minlength="8"` on password, `required` on email, but no visible validation messages shown to user (e.g., "Password must be at least 8 characters") |

**UI/UX Issues:**
- No password visibility toggle (show/hide password)
- No "Remember me" checkbox
- Password minimum length enforcement is HTML-only; no visible error feedback when minlength is violated

**Accessibility:**
- No `aria-live` region on error messages for screen reader announcements
- No `aria-label` on the form or submit button
- Input fields lack explicit `id` attributes linked to `<label for="...">` -- labels use `class="block"` but no `for` attribute
- No `autocomplete="email"` / `autocomplete="current-password"` attributes

---

### 2. DASHBOARD
**File:** `frontend/src/app/features/dashboard/pages/dashboard-page.component.ts`
**PRD Reference:** Section 5.8 Dashboard cards

| # | Dashboard Card (PRD 5.8) | Status | Notes |
|---|--------------------------|--------|-------|
| 1 | Liquidity Risk (Cash Runway, DSCR, risk rating) | PASS | Card with cash_runway_days, dscr, risk_rating with color coding |
| 2 | FX Exposure (locked/floating) | PASS | Card shows total_locked_usd and total_floating_usd |
| 3 | Portfolio Margin (blended margin, target, gap) | PASS | Card with margin bar, target indicator |
| 4 | Orders Pipeline (status counts) | PASS | Iterates pipeline entries |
| 5 | Inventory Alerts | PASS | Shows low-stock alerts with "View all" link |
| 6 | AI Recommendations | PASS | Shows recommendations with priority badges |
| 7 | Global Exposure | PASS | Multi-currency view with EUR/USD/NGN toggle |
| 8 | Logistics Efficiency | PASS | 90-day rolling average with status indicator |
| 9 | Triage/Liquidity Squeeze Alert | PASS | Conditional banner at top when triage is active |

**UI/UX Issues:**
- `Math = Math;` is assigned as a class property (line 346) to use `Math.min` in template -- works but is an Angular anti-pattern; a computed signal or method would be cleaner
- Skeleton loading only shows 4 small + 2 large placeholders; doesn't mirror the actual 9-card layout
- The "Scenario Simulation View" (PRD 5.8) is not on the dashboard -- it's only on the Cashflow page. PRD says it should be a dashboard panel. This is acceptable if the dashboard links to it.

**Accessibility:**
- No `role="alert"` on the Triage Alert banner
- Color-coded values (DSCR green/amber/red) have no text alternative for color-blind users -- the numeric value is shown which partially mitigates this
- No skip-navigation landmarks

**Missing vs PRD:**
- No "trend arrows indicating whether each metric has improved or deteriorated over the past 7 days" (ST-702) -- DSCR and Cash Runway show values but no trend arrows on the dashboard. Global Exposure has a debt_to_trade_ratio arrow but it's based on threshold, not trend.

---

### 3. SALES PAGE
**File:** `frontend/src/app/features/sales/pages/sales-page.component.ts`
**PRD Reference:** ST-301 -- Manual Daily Sales Entry, ST-302, ST-303

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | Quick-entry form with product dropdown | PASS | `<select>` with all products |
| 2 | Quantity input fields | PASS | `type="number"` with `min="1"` |
| 3 | Date field pre-populated with today | PASS | `newRow()` sets `new Date().toISOString().split('T')[0]` |
| 4 | Date adjustable for retroactive entries | PASS | `type="date"` input is editable |
| 5 | Confirmation message after submit | PASS | PrimeNG Toast with severity "success" |
| 6 | Prevents quantity > current stock | MISSING | No stock-level validation in the frontend; form accepts any quantity |
| 7 | Multi-row entry (add/remove rows) | PASS | "Add Row" button; trash button to remove |
| 8 | History log filterable by date/product (ST-303) | PARTIAL | History table shown but **no filters** (no date picker, no product filter) |
| 9 | Edit/Delete on history entries (ST-303) | MISSING | History table is read-only; no Edit or Delete buttons on entries |
| 10 | Bulk CSV upload (ST-302) | MISSING | No CSV upload UI, no template download link |
| 11 | Export button (ST-202) | MISSING | No export/CSV download button on sales page |

**UI/UX Issues:**
- No loading state while history is being fetched
- History is limited to 20 records with no pagination or "load more"
- No total/summary row at the bottom of the history table
- The form does not show which product the entry refers to after submission -- only the toast message

**Accessibility:**
- Labels on row 0 only; subsequent rows have no associated labels (screen readers won't know what each input is)
- `<select>` elements lack `aria-label`
- Table lacks `<caption>` element

---

### 4. PRODUCTS PAGE
**File:** `frontend/src/app/features/products/pages/products-page.component.ts`
**PRD Reference:** General product management (implied by multiple stories)

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | Product table (list view) | PASS | Full table with sortable columns |
| 2 | Grid/card view | PASS | Toggle between grid and list views |
| 3 | Add product | PASS | "Add Product" tab with form |
| 4 | Edit product | PASS | Edit dialog with all fields |
| 5 | Delete product | PASS | Confirmation via action dropdown |
| 6 | Categories management | PASS | Dedicated "Categories" tab |
| 7 | Image upload | PASS | File input on both add and edit forms |
| 8 | Search | PASS | Search bar filters by name and SKU |
| 9 | Pagination | PASS | Full pagination with page size selector |
| 10 | Column visibility toggle | PASS | Dropdown to toggle columns |
| 11 | Sorting | PASS | Click-to-sort on column headers |
| 12 | Category filter | PASS | Filter panel with category dropdown |
| 13 | Status filter (active/inactive) | PASS | Filter panel with status dropdown |
| 14 | CSV export | PASS | "Export CSV" button present |
| 15 | Stock report tab | PASS | Separate tab with stock/margin data |

**CRITICAL:** This entire page is **unreachable** -- no route and no sidebar entry (see Blocking Issue #1 above).

**UI/UX Issues:**
- Image URLs are hardcoded to `http://localhost:8000` -- will break in production
- No image preview in the add/edit forms after file selection
- Delete confirmation is not shown (button calls `confirmDelete(product)` but no confirmation dialog visible in template -- likely handled via PrimeNG ConfirmDialog not imported)
- Deactivate/Activate toggle doesn't show a confirmation

**Accessibility:**
- Action dropdown menus lack `aria-expanded`, `role="menu"`, and `role="menuitem"` attributes
- Column visibility checkboxes lack explicit labels (they have adjacent text but no `for` attribute)
- No `aria-sort` attributes on sortable table headers

---

### 5. INVENTORY PAGE
**File:** `frontend/src/app/features/inventory/pages/inventory-page.component.ts`
**PRD Reference:** Section 5.2.2, ST-401, ST-402

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | Stock levels table | PASS | Table with product, stock, threshold |
| 2 | Low stock threshold display | PASS | Threshold column shown per product |
| 3 | Low stock alert (visual) | PASS | Rows colored red/amber; StatusBadge shows "Critical"/"Low"/"Healthy" |
| 4 | Depletion forecast date | PARTIAL | Column exists, shows `depletion_date` if available, but **no confidence interval** (PRD ST-402 says "Expected stock-out: 15 Mar 2026 +/- 5 days") |
| 5 | Products near stock-out highlighted red | PASS | `stockRowClass()` returns red/amber backgrounds |
| 6 | Movement history | PASS | Recent movements table with type, qty, notes |
| 7 | Stock adjustment dialog | PASS | Modal with type (Purchase/Manual Correction/Damage), quantity, notes |
| 8 | Configurable threshold per product | PARTIAL | Threshold is displayed but there is no UI to **edit** the threshold from this page |
| 9 | Email/push notification for low stock | MISSING | No notification setup UI |

**UI/UX Issues:**
- No search/filter on inventory table
- No pagination on inventory or movements tables
- Movements table has no date range filter
- Adjust dialog does not show a warning when adjusting below threshold

**Accessibility:**
- Table headers lack `scope="col"`
- Status badges rely on color alone; text labels ("Critical"/"Low"/"Healthy") help mitigate
- Dialog lacks `aria-describedby`

---

### 6. ORDERS PAGE
**File:** `frontend/src/app/features/orders/pages/orders-page.component.ts`
**PRD Reference:** ST-501, ST-502, Section 5.3

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | Pipeline view with status columns | PASS | Horizontal pipeline with PENDING, IN_PRODUCTION, SHIPPED, CLEARING, DELIVERED |
| 2 | Order cards in pipeline | PASS | Cards show order_number, supplier, total_usd |
| 3 | Create order form | PASS | Dialog with supplier, items, lead time components |
| 4 | Product/qty/unit cost per item | PASS | Multiple items with product dropdown, qty, $/unit |
| 5 | Lead time components (production/shipping/clearing) | PASS | Three input fields in create dialog |
| 6 | ETA auto-calculated | PARTIAL | `estimated_arrival_date` shown in table, but not visibly calculated in the create form; likely backend-computed |
| 7 | Status transitions | PASS | Detail dialog shows "Move to [next status]" buttons; transitions enforced: PENDING->IN_PRODUCTION->SHIPPED->CLEARING->DELIVERED |
| 8 | FX Exposure per order | PASS | Detail dialog shows locked 30% and floating 70% |
| 9 | Record FX rate on delivery (ST-502) | MISSING | Moving to DELIVERED does not prompt for actual FX rate |
| 10 | Order date field in create form | MISSING | No `order_date` input in the create dialog; only backend may default it |
| 11 | 30% deposit recording at creation (ST-501) | MISSING | No deposit amount or FX rate capture at order creation |
| 12 | Inline product creation | MISSING | No ability to create a new product from within the order create dialog |
| 13 | Profit projection per order | MISSING | No profit projection displayed in order detail |
| 14 | Predicted vs actual FX comparison | MISSING | No side-by-side FX comparison in order detail |

**UI/UX Issues:**
- Pipeline columns are horizontally scrollable but have fixed `min-w-48` -- on mobile, pipeline cards may be cramped
- No search or filter on the "All Orders" table
- No pagination on the orders table
- Create order dialog does not validate required fields visually (no asterisks or error messages)

**Accessibility:**
- Pipeline cards are `<div>` with `(click)` but no `role="button"` or `tabindex`
- Status transition buttons lack `aria-label` describing the action
- Table rows with `(click)` lack keyboard accessibility (`tabindex`, `keydown.enter`)

---

### 7. FX PAGE
**File:** `frontend/src/app/features/fx/pages/fx-page.component.ts`
**PRD Reference:** Section 5.4, ST-601, ST-602, ST-603

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | Current NGN/USD rate card | PASS | Large rate display with date and source |
| 2 | EUR/USD sub-card | PASS | Below the main rate in same card |
| 3 | Manual rate entry | PASS | Form with pair selector (USD/NGN, EUR/USD), rate, date, source |
| 4 | History chart (90 days) | PASS | Line chart via PrimeNG `p-chart` |
| 5 | Forecast chart | PASS | 30-day forecast with base, best, worst case lines |
| 6 | Forecast table with scenarios | PASS | Table with date, base, best, worst columns |
| 7 | Pair selector (USD/NGN, EUR/USD) | PASS | Dropdown in manual entry form |
| 8 | FX alert threshold configuration (ST-603) | MISSING | No UI to set alert thresholds |
| 9 | Per-order FX exposure breakdown (ST-601) | MISSING | No per-order FX view on this page (partially covered in Orders detail) |
| 10 | Export button (ST-202) | MISSING | No CSV export on FX page |

**UI/UX Issues:**
- Forecast is limited to 30 days; PRD specifies 180-day forecast horizon (Section 7.2.1)
- No ability to toggle between different chart time ranges
- EUR/USD history chart is not available (only NGN/USD shown in history)
- No loading skeleton for the rate card -- shows empty skeleton div

**Accessibility:**
- Chart is rendered as `<canvas>` which is inaccessible to screen readers -- no `aria-label` or text alternative
- Form labels are present but not linked via `for`/`id` attributes

---

### 8. CASHFLOW PAGE
**File:** `frontend/src/app/features/cashflow/pages/cashflow-page.component.ts`
**PRD Reference:** ST-701, ST-702, ST-703

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | 6-month projection chart | PASS | Bar chart with inflows, outflows, cumulative line |
| 2 | Month-by-month table (inflows/outflows/net/cumulative) | PASS | Full table with all columns + per-month DSCR |
| 3 | Negative months highlighted red | PASS | `net_cashflow >= 0` conditional coloring |
| 4 | Cash Runway metric | PASS | Displayed in days |
| 5 | DSCR with color coding | PASS | Green >= 1.5, amber 1.0-1.49, red < 1.0 |
| 6 | Risk rating (Low/Medium/High) | PASS | StatusBadge with color |
| 7 | Scenario simulator inputs (FX shock, demand drop) | PASS | Two input fields + preset buttons |
| 8 | Pre-set scenarios: FX +10%, FX +20%, Demand -20% | PARTIAL | Has FX +10%, FX +20%, Demand -20%, but **missing Demand -10% and Combined stress** buttons |
| 9 | Scenario results (worst DSCR, cash runway) | PARTIAL | Shows worst_dscr and cash_runway_days, but **missing portfolio margin impact** |
| 10 | Scenario save/compare side-by-side (ST-703) | MISSING | No save or compare functionality |
| 11 | Trend arrows on metrics (ST-702) | MISSING | No trend arrows showing 7-day improvement/deterioration |
| 12 | Alerts section | PASS | Conditional alert banners based on severity |

**UI/UX Issues:**
- Scenario result card replaces previous result -- no history of simulations
- Cumulative cashflow chart could benefit from a zero-line reference for clarity
- Cash Runway shown in "days" but PRD ST-702 says "displayed in months"

**Accessibility:**
- Chart `<canvas>` has no text alternative
- Alert banners lack `role="alert"`
- Color-coded DSCR values in the table need the text fallback (numeric value helps)

---

### 9. PRICING PAGE
**File:** `frontend/src/app/features/pricing/pages/pricing-page.component.ts`
**PRD Reference:** ST-801, ST-802, Section 5.6

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | Blended portfolio margin card | PASS | Large display with gap from target |
| 2 | Per-product margins table | PASS | Table with cost, selling, margin, target, gap |
| 3 | Margin distribution chart | PASS | Bar chart bucketing products by margin range |
| 4 | Price adjustment recommendations | PASS | Cards with Apply/Dismiss buttons |
| 5 | Products below margin highlighted | PASS | Red background on rows where gap < 0 |
| 6 | Cross-subsidisation display (ST-801) | MISSING | PRD says "Product A margin (42%) offsets Product B margin (28%)" -- no such display |
| 7 | Apply updates price in real-time (ST-801) | PARTIAL | Apply calls the service, but the page does not reload margin data after application |
| 8 | Demand elasticity configuration (ST-802) | MISSING | No elasticity coefficient fields, no FX sensitivity fields, no tooltips |
| 9 | Dynamic pricing updates as FX changes | MISSING | No real-time update mechanism |

**UI/UX Issues:**
- No search or filter on the product margins table
- No pagination on the margins table
- Distribution chart has axis labeled "Products" on Y but it's a vertical bar chart -- the Y axis should be "Count"

**Accessibility:**
- Chart `<canvas>` lacks text alternative
- Recommendation cards lack `role="article"` or similar landmark

---

### 10. RECOMMENDATIONS PAGE
**File:** `frontend/src/app/features/recommendations/pages/recommendations-page.component.ts`
**PRD Reference:** ST-901, Section 5.7

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | Ranked list ordered by financial urgency | PASS | List rendered from API (ordering is server-side) |
| 2 | Category display (price/order/hedge/inventory/liquidity) | PASS | Category text + icon per recommendation |
| 3 | Category filter pills | PASS | ALL, PRICING, INVENTORY, FX, CASHFLOW, ORDERS |
| 4 | Priority badges | PASS | HIGH/MEDIUM/LOW with StatusBadge |
| 5 | Apply action button | PASS | Green "Apply" button per recommendation |
| 6 | Dismiss with reason | PASS | Dismiss opens dialog requiring reason text |
| 7 | History toggle | PASS | "Show History" button loads archived recommendations |
| 8 | Expected impact display | PASS | Impact key-value pairs rendered |
| 9 | Refresh / Generate button | PASS | "Generate New" button with loading state |
| 10 | "One-click action button" per recommendation (ST-901) | PASS | Apply button serves this purpose |
| 11 | Impact summary cards | PASS | Pending count, revenue impact, cost savings |
| 12 | "Refresh" button (ST-901 says on-demand refresh) | PARTIAL | "Generate New" exists but is labeled as generation, not refresh of existing |
| 13 | Category includes "HEDGE" and "LIQUIDITY" (ST-901) | PARTIAL | Filter categories are PRICING, INVENTORY, FX, CASHFLOW, ORDERS -- missing "HEDGE" and "LIQUIDITY" as distinct categories |

**UI/UX Issues:**
- No pagination on recommendations list
- No search/filter by text
- Dismissed recommendations are filtered out client-side; applying many recs may cause stale data

**Accessibility:**
- Dismiss dialog textarea lacks `aria-label`
- Category filter buttons lack `role="tab"` / `aria-selected`
- Recommendation cards use hover shadow but are not focusable via keyboard

---

### 11. SIDEBAR
**File:** `frontend/src/app/layout/sidebar/sidebar.component.ts`

| # | Requirement | Status | Notes |
|---|-------------|--------|-------|
| 1 | All feature pages linked | FAIL | **Missing "Products" nav item** (8 of 9 present) |
| 2 | Active route highlighting | PASS | `routerLinkActive` with primary color styles |
| 3 | Mobile overlay | PASS | Shell component has backdrop overlay + sidebar translate animation |
| 4 | Collapsible on mobile | PASS | `mobileOpen` input toggles translate-x |
| 5 | Desktop persistent | PASS | `lg:static lg:translate-x-0` |

**UI/UX Issues:**
- No user profile section or logout button in the sidebar
- No settings/configuration link (PRD ST-102 mentions settings menu for API key)
- Version text "ModishLog v1.0" at bottom -- no utility

**Accessibility:**
- `<nav>` element is present, which is good
- No `aria-label="Main navigation"` on the `<nav>` element
- No `aria-current="page"` on active links (Angular's routerLinkActive doesn't add this by default)
- Mobile close button relies on `(click)` on the backdrop; no explicit close button on the sidebar itself

---

### 12. SHARED COMPONENTS

#### StatusBadgeComponent
**File:** `frontend/src/app/shared/components/status-badge/status-badge.component.ts`
- **PASS**: Clean implementation with 5 severity levels (success, warning, danger, info, neutral)
- Accessible: text is always visible alongside color

#### MetricCardComponent
**File:** `frontend/src/app/shared/components/metric-card/metric-card.component.ts`
- **PASS**: Title, value, trend arrow, severity border
- **Note**: Not used by any page component (all dashboards build cards inline). This is dead code.

#### DataTableComponent
**File:** `frontend/src/app/shared/components/data-table/data-table.component.ts`
- **PASS**: Generic table with columns/data inputs, empty state
- **Note**: Not used by any page component. All pages build tables inline. This is dead code.

#### AlertBannerComponent
**File:** `frontend/src/app/shared/components/alert-banner/alert-banner.component.ts`
- **PASS**: Dismissible banner with severity (info/success/warning/danger)
- **Note**: Not used by any page component. Cashflow page builds alerts inline. This is dead code.

---

## SUMMARY OF FINDINGS

### Requirements FULLY MET (by component):
- **Dashboard**: 9/9 dashboard cards present (Liquidity, FX, Margin, Pipeline, Alerts, Recommendations, Global Exposure, Logistics, Triage)
- **Sales**: Quick-entry form with product dropdown, quantity, date, confirmation toast
- **Inventory**: Stock levels table, low stock alerts, depletion date column, movement history, adjust dialog
- **Orders**: Pipeline view, create form with items and lead times, status transitions, FX exposure per order
- **FX**: Current rate card, EUR/USD sub-card, manual entry, pair selector, history chart, forecast chart
- **Cashflow**: 6-month projection chart + table, DSCR/Runway/Risk, scenario simulator
- **Pricing**: Blended margin card, per-product table, distribution chart, recommendations with Apply/Dismiss
- **Recommendations**: Category pills, priority badges, apply/dismiss, history toggle, generate new

### Requirements MISSING or PARTIALLY met:

| Priority | Item | Component | PRD Ref |
|----------|------|-----------|---------|
| **CRITICAL** | Products page unreachable (no route, no sidebar link) | Router + Sidebar | -- |
| HIGH | No "Forgot password" flow | Login | ST-101 |
| HIGH | No lockout countdown timer (just a message) | Login | ST-101 |
| HIGH | No stock-level validation on sales entry | Sales | ST-301 |
| HIGH | No Edit/Delete on sales history entries | Sales | ST-303 |
| HIGH | No CSV bulk upload for sales | Sales | ST-302 |
| HIGH | No FX rate prompt when order moves to DELIVERED | Orders | ST-502 |
| HIGH | No order_date field in create form | Orders | ST-501 |
| HIGH | No 30% deposit/FX rate recording at order creation | Orders | ST-501 |
| HIGH | No FX alert threshold configuration UI | FX | ST-603 |
| HIGH | No demand elasticity configuration | Pricing | ST-802 |
| HIGH | No cross-subsidisation display | Pricing | ST-801 |
| MEDIUM | No export buttons on Sales and FX pages | Sales, FX | ST-202 |
| MEDIUM | No Demand -10% and Combined stress pre-set buttons | Cashflow | ST-703 |
| MEDIUM | No scenario save/compare side-by-side | Cashflow | ST-703 |
| MEDIUM | No trend arrows on liquidity metrics (7-day) | Cashflow, Dashboard | ST-702 |
| MEDIUM | Cash Runway in "days" not "months" as PRD specifies | Cashflow | ST-702 |
| MEDIUM | No portfolio margin impact in scenario results | Cashflow | ST-703 |
| MEDIUM | No per-order FX scenario view (best/base/worst) | FX/Orders | ST-602 |
| MEDIUM | No inline product creation in order dialog | Orders | -- |
| MEDIUM | Forecast limited to 30 days (PRD says 180 days) | FX | 7.2.1 |
| MEDIUM | No depletion forecast confidence interval | Inventory | ST-402 |
| MEDIUM | No editable threshold per product | Inventory | ST-401 |
| MEDIUM | No settings page (API key, alert thresholds) | Sidebar/App | ST-102, ST-603 |
| LOW | 3 shared components (MetricCard, DataTable, AlertBanner) are dead code | Shared | -- |
| LOW | Hardcoded localhost:8000 in product image URLs | Products | -- |
| LOW | No pagination on Inventory, Orders, Movements tables | Multiple | -- |

### Accessibility (cross-cutting):
| Issue | Affected Components |
|-------|-------------------|
| Zero `aria-*` attributes across all templates | ALL |
| No `role="alert"` on error/warning banners | Login, Cashflow, Dashboard |
| Chart `<canvas>` elements have no text alternatives | FX, Cashflow, Pricing |
| Form labels not linked via `for`/`id` pairs | Login, Sales, Orders, FX, Inventory, Products |
| Interactive `<div>` elements with `(click)` lack `role="button"` and `tabindex` | Orders, Products, Dashboard |
| No `aria-label` on `<nav>` element | Sidebar |
| No keyboard navigation support on dropdown menus | Products |
| No `<caption>` on data tables | ALL tables |
| No skip-to-content link | Shell |

---

## RECOMMENDATIONS (Prioritized)

1. **[CRITICAL]** Add Products route to `app.routes.ts` and Products nav item to sidebar
2. **[HIGH]** Implement "Forgot Password" link and flow on Login page
3. **[HIGH]** Add lockout countdown timer component on Login page
4. **[HIGH]** Add stock-level validation to Sales entry form (compare with current inventory)
5. **[HIGH]** Add Edit/Delete functionality to Sales history entries
6. **[HIGH]** Add FX rate prompt dialog when transitioning order to DELIVERED
7. **[HIGH]** Add order_date field and deposit FX rate capture to order create form
8. **[HIGH]** Build Settings page with FX alert thresholds and API key configuration
9. **[HIGH]** Add demand elasticity coefficient fields to Pricing page
10. **[MEDIUM]** Add CSV export buttons to Sales and FX pages
11. **[MEDIUM]** Add Demand -10% and Combined stress preset buttons to Cashflow simulator
12. **[MEDIUM]** Add scenario save/compare functionality to Cashflow page
13. **[MEDIUM]** Add trend arrows (7-day delta) to Cash Runway and DSCR displays
14. **[MEDIUM]** Extend FX forecast horizon to 180 days per PRD specification
15. **[MEDIUM]** Add depletion forecast confidence interval display to Inventory page
16. **[LOW]** Replace hardcoded localhost:8000 with environment-variable-based API URL
17. **[LOW]** Add pagination to Inventory, Orders, and Movements tables
18. **[LOW]** Audit and add ARIA attributes across all components for WCAG compliance
19. **[LOW]** Remove or integrate unused shared components (MetricCard, DataTable, AlertBanner)
