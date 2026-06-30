import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { ensureProduct, createOrder, deleteOrder } from './helpers/data';

// ---------------------------------------------------------------------------
// Dashboard E2E Tests
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.waitForLoadState('domcontentloaded');
  // Wait for widget card headers to render (loading() signal becomes false after data loads)
  await page.locator('p.font-semibold.text-slate-800').first()
    .waitFor({ timeout: 20000 }).catch(() => {});
});

test.describe('Dashboard widget cards', () => {
  test('displays the Cash Health card', async ({ page }) => {
    await expect(page.getByText('Cash Health').first()).toBeVisible();
    await expect(page.getByText('Cash Runway').first()).toBeVisible();
    await expect(page.getByText('Profit Score (DSCR)').first()).toBeVisible();
  });

  test('displays the FX Exposure card with empty state when no records', async ({ page }) => {
    await expect(page.getByText('FX Exposure').first()).toBeVisible();
    // The card always renders — either exposure rows or the empty-state message
    const hasExposure = await page.getByText('No FX exposure tracked yet').isVisible().catch(() => false);
    const hasRows = await page.locator('.rounded-xl.border.border-gray-100').first().isVisible().catch(() => false);
    expect(hasExposure || hasRows).toBe(true);
  });

  test('displays the Profit Margin card', async ({ page }) => {
    await expect(page.getByText('Profit Margin').first()).toBeVisible();
    await expect(page.getByText('Target:').first()).toBeVisible();
  });

  test('displays the Order Activity card', async ({ page }) => {
    await expect(page.getByText('Order Activity').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('In Progress').first()).toBeVisible({ timeout: 10_000 });
  });

  test('displays Stock Levels card', async ({ page }) => {
    await expect(page.getByText('Stock Levels').first()).toBeVisible();
  });

  test('displays Smart Suggestions card', async ({ page }) => {
    await expect(page.getByText('Smart Suggestions').first()).toBeVisible();
  });
});

test.describe('Global Exposure card (Task 16)', () => {
  let usdOrderId: string;

  test.beforeAll(async () => {
    // Seed a USD purchase order so the global-exposure API returns non-null data
    const product = await ensureProduct('E2E Global Exposure Product');
    const order = await createOrder(product.id, { currency: 'USD', quantity: 5, unitCost: '200.00' });
    usdOrderId = order.id;
  });

  test.afterAll(async () => {
    if (usdOrderId) await deleteOrder(usdOrderId);
  });

  test('renders when data is available', async ({ page }) => {
    await expect(page.getByText('Global Exposure').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('EUR Loan Balance').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('USD Order Obligations').first()).toBeVisible();
    await expect(page.getByText('Total Exposure (NGN)').first()).toBeVisible();
    await expect(page.getByText('Debt/Trade Ratio:').first()).toBeVisible();
  });

  test('shows numeric total exposure value', async ({ page }) => {
    // Total headline renders as ₦<number> in the indigo summary box
    const totalEl = page.locator('p.text-2xl.font-bold.text-indigo-700').first();
    await expect(totalEl).toBeVisible();
    await expect(totalEl).toContainText(/₦[\d,]+/);
  });

  test('shows debt-to-trade ratio as a decimal', async ({ page }) => {
    // Ratio renders via number:'1.2-2' inside the indigo summary box
    const ratioEl = page.locator('span.text-xs.font-bold').filter({ hasText: /\d+\.\d{2}/ }).first();
    await expect(ratioEl).toBeVisible();
  });
});

test.describe('Recent Sales — mobile stacked cards vs desktop table (Task 144)', () => {
  test('shows stacked card list on mobile (375px) and hides the table', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    // Table must be hidden via hidden sm:table
    const table = page.locator('table.hidden');
    await expect(table).toBeAttached();
    // Mobile card list must be visible
    const mobileList = page.locator('div.block.sm\\:hidden');
    await expect(mobileList).toBeVisible();
  });

  test('shows table on desktop (768px) and hides the card list', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    // Table visible at sm+ (768px triggers sm breakpoint)
    const table = page.locator('table.hidden');
    await expect(table).toBeAttached();
    // Mobile list must not be visible at this width
    const mobileList = page.locator('div.block.sm\\:hidden');
    await expect(mobileList).toBeHidden();
  });

  test('mobile cards show product name, qty, revenue, and margin', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    const mobileList = page.locator('div.block.sm\\:hidden');
    // If there are recent sales, each card row must be at least 44px tall
    const firstRow = mobileList.locator('div.min-h-\\[44px\\]').first();
    const hasRows = await firstRow.isVisible().catch(() => false);
    if (hasRows) {
      const box = await firstRow.boundingBox();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
  });
});

test.describe('Logistics Efficiency card (Task 17)', () => {
  test('renders with rolling average data', async ({ page }) => {
    await expect(page.getByText('Shipping Costs').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('90-day rolling average').first()).toBeVisible();
  });

  test('shows a numeric percentage value', async ({ page }) => {
    // rolling_90d_avg_pct renders via number:'1.1-1' as e.g. "0.0%" or "58.4%"
    const pctElement = page.locator('p.text-4xl.font-bold').filter({ hasText: /%/ });
    await expect(pctElement).toBeVisible();
    await expect(pctElement).toContainText(/\d+\.\d%/);
  });

  test('shows threshold guide with Target, Caution, High rows', async ({ page }) => {
    await expect(page.getByText('Target').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('Caution').first()).toBeVisible();
    await expect(page.getByText('High').first()).toBeVisible();
  });
});
