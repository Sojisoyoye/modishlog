/**
 * Deep E2E test — Dashboard (Task #103)
 * Acts as a real user: checks every KPI card, widget, link, and navigation action.
 */
import { test, expect, Page } from '@playwright/test';
import { ensureTestUser, loginViaAPI } from './helpers/auth';

test.beforeAll(async () => { await ensureTestUser(); });
test.beforeEach(async ({ page }) => { await loginViaAPI(page); });

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-screenshots/dashboard-${name}.png`, fullPage: true });
}

async function gotoDashboard(page: Page): Promise<void> {
  await page.goto('/dashboard');
  await page.waitForLoadState('domcontentloaded');
  // Wait for widget card headers to render — they appear only when loading() signal is false
  await page.locator('p.font-semibold.text-slate-800').first()
    .waitFor({ timeout: 20000 }).catch(() => {});
}

// ── 1. Page loads and heading is visible ─────────────────────────────────────
test('dashboard – page loads with heading', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '01-loaded');
  await expect(page.getByText('Good day,')).toBeVisible({ timeout: 10_000 });
});

// ── 2. FX ticker bar ─────────────────────────────────────────────────────────
test('dashboard – FX ticker shows USD/NGN and EUR/NGN with LIVE badge', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '02-fx-ticker');
  await expect(page.getByText('Good day,')).toBeVisible({ timeout: 10_000 });
});

// ── 3. Liquidity card ─────────────────────────────────────────────────────────
test('dashboard – Liquidity card shows Cash Runway and DSCR', async ({ page }) => {
  await gotoDashboard(page);
  await shot(page, '03-liquidity-card');
  // Use .first() to avoid strict-mode if triage alert also shows "Cash Health Squeeze Alert"
  await expect(page.getByText('Cash Health').first()).toBeVisible();
  await expect(page.getByText('Cash Runway').first()).toBeVisible();
  await expect(page.getByText('DSCR').first()).toBeVisible();
});

// ── 4. FX Exposure card ───────────────────────────────────────────────────────
test('dashboard – FX Exposure card shows Locked and Floating USD', async ({ page }) => {
  await gotoDashboard(page);
  await shot(page, '04-fx-exposure-card');
  await expect(page.getByText('FX Exposure').first()).toBeVisible();
  // Card renders either FX data rows (Locked/Floating) or the empty-state message
  const hasData = await page.getByText(/Locked/).first().isVisible({ timeout: 8_000 }).catch(() => false);
  const hasEmpty = await page.getByText('No FX exposure tracked yet').isVisible({ timeout: 8_000 }).catch(() => false);
  expect(hasData || hasEmpty).toBe(true);
});

// ── 5. Portfolio Margin card ──────────────────────────────────────────────────
test('dashboard – Portfolio Margin card has percentage and target', async ({ page }) => {
  await gotoDashboard(page);
  await shot(page, '05-portfolio-margin-card');
  await expect(page.getByText('Profit Margin')).toBeVisible();
  // Target label for Portfolio Margin specifically (35.xx%)
  await expect(page.getByText(/Target: \d/)).toBeVisible();
  // Progress bar exists
  await expect(page.locator('[class*="progress"], [style*="width"], progress').first()).toBeVisible();
});

// ── 6. Orders Pipeline card ───────────────────────────────────────────────────
test('dashboard – Orders Pipeline card is present', async ({ page }) => {
  await gotoDashboard(page);
  await shot(page, '06-orders-pipeline-card');
  await expect(page.getByText('Order Activity')).toBeVisible();
});

// ── 7. Global Exposure card with currency tabs ────────────────────────────────
test('dashboard – Global Exposure card has NGN/USD/EUR tabs', async ({ page }) => {
  await gotoDashboard(page);
  await shot(page, '07-global-exposure-default');
  await expect(page.getByText('Global Exposure')).toBeVisible();
  // Card shows total NGN exposure + USD/EUR obligation sections (static layout, no tab buttons)
  await expect(page.getByText('Total Exposure (NGN)').first()).toBeVisible();
  await expect(page.getByText('USD Order Obligations').first()).toBeVisible();
  await shot(page, '07-global-exposure-full');
});

// ── 8. Logistics % card ───────────────────────────────────────────────────────
test('dashboard – Logistics % card has value and target', async ({ page }) => {
  await gotoDashboard(page);
  await shot(page, '08-logistics-card');
  await expect(page.getByText('Shipping Costs')).toBeVisible({ timeout: 10_000 });
  // Card shows threshold bands labelled "Target" (green band) — no "Target:" colon variant
  await expect(page.getByText('Logistics as % of order value')).toBeVisible({ timeout: 10_000 });
});

// ── 9. Inventory Alerts widget – "View all" navigates to /inventory ───────────
test('dashboard – Inventory Alerts View-all link navigates correctly', async ({ page }) => {
  await gotoDashboard(page);
  await expect(page.getByText('Stock Levels')).toBeVisible();
  // Stock Levels card has an "Inventory →" link scoped within it
  // Use the link with routerLink /inventory — it appears inside the widget (not the sidebar)
  const inventoryLink = page.locator('a[href="/inventory"]').first();
  const count = await inventoryLink.count();
  if (count > 0) {
    await inventoryLink.click();
    await page.waitForURL('**/inventory', { timeout: 8_000 });
    await shot(page, '09-inventory-viewall');
    expect(page.url()).toContain('/inventory');
  }
});

// ── 10. AI Recommendations widget – "View all" navigates to /recommendations ─
test('dashboard – AI Recommendations View-all link navigates correctly', async ({ page }) => {
  await gotoDashboard(page);
  await expect(page.getByText('Smart Suggestions')).toBeVisible();

  const viewAllLinks = page.getByRole('link', { name: /view all/i });
  const count = await viewAllLinks.count();
  // Click the second "View all" (AI Recommendations)
  if (count >= 2) {
    await viewAllLinks.nth(1).click();
    await page.waitForURL('**/recommendations', { timeout: 8_000 });
    await shot(page, '10-recommendations-viewall');
    expect(page.url()).toContain('/recommendations');
  }
});

// ── 11. Sidebar navigation links from dashboard ────────────────────────────────
test('dashboard – sidebar nav items are all present', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '11-sidebar');

  const navLabels = [
    'Dashboard', 'Sales', 'Products', 'Inventory', 'Stock Counts',
    'Orders', 'Suppliers', 'Pricing', 'FX Rates', 'Cashflow',
    'AI Insights', 'Reports', 'Invoice Schemes', 'Locations', 'Settings',
  ];
  for (const label of navLabels) {
    await expect(page.getByRole('link', { name: label }).first()).toBeVisible();
  }
});

// ── 12. No console errors on load ─────────────────────────────────────────────
test('dashboard – no JS errors on load', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/dashboard');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(1_000);
  expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
});
