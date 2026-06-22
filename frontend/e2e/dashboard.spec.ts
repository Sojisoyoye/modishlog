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
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
});

test.describe('Dashboard cards', () => {
  test('displays the Liquidity card', async ({ page }) => {
    await expect(page.getByText('Liquidity').first()).toBeVisible();
    await expect(page.getByText('Cash Runway').first()).toBeVisible();
    await expect(page.getByText('DSCR').first()).toBeVisible();
  });

  test('displays the FX Exposure card', async ({ page }) => {
    await expect(page.getByText('FX Exposure').first()).toBeVisible();
    await expect(page.getByText('Locked (USD)').first()).toBeVisible();
    await expect(page.getByText('Floating (USD)').first()).toBeVisible();
  });

  test('displays the Portfolio Margin card', async ({ page }) => {
    await expect(page.getByText('Portfolio Margin').first()).toBeVisible();
    await expect(page.getByText('Target:').first()).toBeVisible();
  });

  test('displays the Orders Pipeline card', async ({ page }) => {
    await expect(page.getByText('Orders Pipeline').first()).toBeVisible();
  });

  test('displays Inventory Alerts card', async ({ page }) => {
    await expect(page.getByText('Inventory Alerts').first()).toBeVisible();
  });

  test('displays AI Recommendations card', async ({ page }) => {
    await expect(page.getByText('AI Recommendations').first()).toBeVisible();
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
    // outer beforeEach already logged in and navigated to /dashboard
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Global Exposure').first()).toBeVisible();
    await expect(page.getByText('EUR Debt').first()).toBeVisible();
    await expect(page.getByText('USD Obligations').first()).toBeVisible();
    await expect(page.getByText('Total Exposure (NGN)').first()).toBeVisible();
    await expect(page.getByText('Debt/Trade Ratio').first()).toBeVisible();
  });

  test('shows numeric values for exposure amounts', async ({ page }) => {
    await page.waitForLoadState('networkidle');

    // The Total Exposure (NGN) value is the only text-primary bold number in the card.
    // With a seeded USD order it must be a non-zero formatted integer (e.g. "1,000,000").
    const totalExposureValue = page.locator('p.text-lg.font-bold.text-primary').first();
    await expect(totalExposureValue).toBeVisible();
    await expect(totalExposureValue).toHaveText(/[\d,]+/);

    // Debt/Trade Ratio renders as a decimal formatted by number:'1.2-2' (e.g. "0.00")
    await expect(page.getByText(/^\d+\.\d{2}$/).first()).toBeVisible();
  });

  test('currency toggle buttons are present when card renders', async ({ page }) => {
    await page.waitForLoadState('networkidle');

    await expect(page.getByRole('button', { name: 'NGN' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'USD' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'EUR' })).toBeVisible();
  });

  test('clicking currency toggle changes active button styling', async ({ page }) => {
    await page.waitForLoadState('networkidle');

    const usdButton = page.getByRole('button', { name: 'USD' });
    await expect(usdButton).toBeVisible();
    await usdButton.click();
    await expect(usdButton).toHaveClass(/bg-primary/);
  });
});

test.describe('Logistics % card (Task 17)', () => {
  test('renders with rolling average data', async ({ page }) => {
    // The logistics-efficiency API always returns a dict (with 0 values when no orders exist),
    // so this card always renders after the page loads.
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Logistics %').first()).toBeVisible();
    await expect(page.getByText('90-day rolling average').first()).toBeVisible();
  });

  test('shows a numeric percentage value', async ({ page }) => {
    await page.waitForLoadState('networkidle');

    // The rolling_90d_avg_pct value renders via Angular's number:'1.1-1' pipe followed by '%'
    // e.g. "0.0%" or "5.3%". This assertion fails if the API crashes or the template breaks.
    const pctElement = page.locator('p.text-3xl.font-bold').filter({ hasText: /%/ });
    await expect(pctElement).toBeVisible();
    await expect(pctElement).toHaveText(/^\d+\.\d%$/);
  });
});

test.describe('Triage banner (Task 21)', () => {
  test('banner is hidden when no active triage condition exists', async ({ page }) => {
    // No triage conditions are seeded in CI — verify the banner is absent.
    // This assertion fails if the banner renders unexpectedly (e.g. due to stale DB state).
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Liquidity Squeeze Alert')).not.toBeVisible();
  });
});
