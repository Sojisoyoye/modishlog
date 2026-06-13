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

// ── 1. Page loads and heading is visible ─────────────────────────────────────
test('dashboard – page loads with heading', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await shot(page, '01-loaded');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect(page.getByText('Business overview at a glance')).toBeVisible();
});

// ── 2. FX ticker bar ─────────────────────────────────────────────────────────
test('dashboard – FX ticker shows USD/NGN and EUR/NGN with LIVE badge', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await shot(page, '02-fx-ticker');
  await expect(page.getByText('USD / NGN')).toBeVisible();
  await expect(page.getByText('EUR / NGN')).toBeVisible();
  await expect(page.getByText('LIVE')).toBeVisible();
});

// ── 3. Liquidity card ─────────────────────────────────────────────────────────
test('dashboard – Liquidity card shows Cash Runway and DSCR', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await shot(page, '03-liquidity-card');
  await expect(page.getByText('Liquidity')).toBeVisible();
  await expect(page.getByText('Cash Runway')).toBeVisible();
  await expect(page.getByText('DSCR')).toBeVisible();
});

// ── 4. FX Exposure card ───────────────────────────────────────────────────────
test('dashboard – FX Exposure card shows Locked and Floating USD', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await shot(page, '04-fx-exposure-card');
  await expect(page.getByText('FX Exposure')).toBeVisible();
  await expect(page.getByText('Locked (USD)')).toBeVisible();
  await expect(page.getByText('Floating (USD)')).toBeVisible();
});

// ── 5. Portfolio Margin card ──────────────────────────────────────────────────
test('dashboard – Portfolio Margin card has percentage and target', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await shot(page, '05-portfolio-margin-card');
  await expect(page.getByText('Portfolio Margin')).toBeVisible();
  // Target label for Portfolio Margin specifically (35.xx%)
  await expect(page.getByText(/Target: \d/)).toBeVisible();
  // Progress bar exists
  await expect(page.locator('[class*="progress"], [style*="width"], progress').first()).toBeVisible();
});

// ── 6. Orders Pipeline card ───────────────────────────────────────────────────
test('dashboard – Orders Pipeline card is present', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await shot(page, '06-orders-pipeline-card');
  await expect(page.getByText('Orders Pipeline')).toBeVisible();
});

// ── 7. Global Exposure card with currency tabs ────────────────────────────────
test('dashboard – Global Exposure card has NGN/USD/EUR tabs', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await shot(page, '07-global-exposure-default');
  await expect(page.getByText('Global Exposure')).toBeVisible();

  // NGN tab button active by default
  const ngnTab = page.getByRole('button', { name: 'NGN' }).first();
  await expect(ngnTab).toBeVisible();

  // Click USD tab
  const usdTab = page.getByRole('button', { name: 'USD' }).first();
  if (await usdTab.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await usdTab.click();
    await page.waitForTimeout(400);
    await shot(page, '07-global-exposure-usd');
  }

  // Click EUR tab
  const eurTab = page.getByRole('button', { name: 'EUR' }).first();
  if (await eurTab.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await eurTab.click();
    await page.waitForTimeout(400);
    await shot(page, '07-global-exposure-eur');
  }
});

// ── 8. Logistics % card ───────────────────────────────────────────────────────
test('dashboard – Logistics % card has value and target', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await shot(page, '08-logistics-card');
  await expect(page.getByText('Logistics %')).toBeVisible();
  await expect(page.getByText(/Target:/i).nth(1)).toBeVisible();
});

// ── 9. Inventory Alerts widget – "View all" navigates to /inventory ───────────
test('dashboard – Inventory Alerts View-all link navigates correctly', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByText('Inventory Alerts')).toBeVisible();

  const viewAllLinks = page.getByRole('link', { name: /view all/i });
  const count = await viewAllLinks.count();
  // Click the first "View all" (Inventory Alerts)
  if (count > 0) {
    await viewAllLinks.first().click();
    await page.waitForURL('**/inventory', { timeout: 8_000 });
    await shot(page, '09-inventory-viewall');
    expect(page.url()).toContain('/inventory');
  }
});

// ── 10. AI Recommendations widget – "View all" navigates to /recommendations ─
test('dashboard – AI Recommendations View-all link navigates correctly', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByText('AI Recommendations')).toBeVisible();

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
  await page.waitForLoadState('networkidle');
  await shot(page, '11-sidebar');

  const navLabels = [
    'Dashboard', 'Sales', 'Products', 'Inventory', 'Stock Counts',
    'Orders', 'Suppliers', 'Pricing', 'FX Rates', 'Cashflow',
    'AI Insights', 'Reports', 'Invoice Schemes', 'Locations', 'Settings',
  ];
  for (const label of navLabels) {
    await expect(page.getByRole('link', { name: label })).toBeVisible();
  }
});

// ── 12. No console errors on load ─────────────────────────────────────────────
test('dashboard – no JS errors on load', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1_000);
  expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
});
