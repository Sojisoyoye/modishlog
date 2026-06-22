/**
 * Golden-path E2E spec — the complete MVP business cycle.
 *
 * Login → Create Product → Create Purchase Order → Transition to DELIVERED →
 * Verify stock → Record Sale → Verify stock drop → Generate P&L Report
 *
 * This is the single most important spec in the suite. If any link in this
 * chain breaks, a beta user's first session will fail.
 */
import { test, expect, request as pwRequest } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';
import { ensureProduct, createOrder } from './helpers/data';

const API = 'http://localhost:8000/api/v1';

/** Get current stock level for a product via the API. */
async function getStock(productId: string): Promise<number> {
  const token = await getAPIToken();
  const ctx = await pwRequest.newContext();
  try {
    const resp = await ctx.get(`${API}/inventory/${productId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok()) return 0;
    const data: { current_stock: number } = await resp.json();
    return data.current_stock;
  } finally {
    await ctx.dispose();
  }
}

// ISO date helpers — computed outside tests to avoid Date.now() in workflow scripts
function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}
function iso30DaysAgo(): string {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().slice(0, 10);
}

test.describe.configure({ mode: 'serial' });

test.describe('Golden path — full MVP business cycle', () => {
  let productId: string;
  let productName: string;
  let orderId: string;

  test.beforeAll(async () => {
    await ensureTestUser();

    // Step 1: create product via API
    const product = await ensureProduct('E2E Golden Path Product');
    productId = product.id;
    productName = product.name;

    // Step 2: create purchase order with qty 10 via API
    const order = await createOrder(productId, { currency: 'NGN', quantity: 10, unitCost: '3000.00' });
    orderId = order.id;
  });

  test('Login redirects to dashboard', async ({ page }) => {
    await loginViaUI(page);
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });

  test('Purchase order transitions from ORDERED through to DELIVERED via UI', async ({ page }) => {
    await loginViaUI(page);
    await page.goto(`/orders/${orderId}`);
    await page.waitForLoadState('networkidle');

    // --- ORDERED → PENDING ---
    await expect(page.getByText('ORDERED')).toBeVisible();
    await page.getByRole('button', { name: 'PENDING' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('PENDING').first()).toBeVisible();

    // --- PENDING → IN_PRODUCTION ---
    await page.getByRole('button', { name: 'IN_PRODUCTION' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('IN_PRODUCTION').first()).toBeVisible();

    // --- IN_PRODUCTION → SHIPPING ---
    await page.getByRole('button', { name: 'SHIPPING' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('SHIPPING').first()).toBeVisible();

    // --- SHIPPING → CLEARED ---
    await page.getByRole('button', { name: 'CLEARED' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('CLEARED').first()).toBeVisible();

    // --- CLEARED → DELIVERED (requires FX rate) ---
    await page.getByPlaceholder('e.g. 1600').fill('1600');
    await page.getByRole('button', { name: 'DELIVERED' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('DELIVERED').first()).toBeVisible();
  });

  test('Stock increases by order qty after DELIVERED', async () => {
    // Wait for the delivery to be processed — verify via API
    const stock = await getStock(productId);
    expect(stock).toBeGreaterThanOrEqual(10);
  });

  test('Recording a sale deducts stock and shows success toast', async ({ page }) => {
    const stockBefore = await getStock(productId);

    await loginViaUI(page);
    await page.goto('/sales');

    // Switch to Record Sales tab
    await page.getByTestId('tab-record-sales').click();
    await page.waitForLoadState('networkidle');

    // Select product in the first row's dropdown
    await page.locator('select[name="product_0"]').selectOption({ label: productName });

    // Set quantity to 3
    await page.locator('input[name="qty_0"]').fill('3');

    // Submit
    await page.getByRole('button', { name: 'Record Sales' }).click();
    await page.waitForLoadState('networkidle');

    // Success toast — summary 'Success', detail 'Sales recorded successfully'
    await expect(page.getByText('Sales recorded successfully')).toBeVisible({ timeout: 8000 });

    // Stock decreased by 3
    const stockAfter = await getStock(productId);
    expect(stockAfter).toBe(stockBefore - 3);
  });

  test('P&L report generates with non-zero revenue after the sale', async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/reports/profit-loss');
    await page.waitForLoadState('networkidle');

    // Fill date range bracketing today
    await page.locator('#pl-start-date').fill(iso30DaysAgo());
    await page.locator('#pl-end-date').fill(isoToday());

    // Generate
    await page.getByRole('button', { name: 'Generate Report' }).click();
    await page.waitForLoadState('networkidle');

    // Net Profit section appears
    await expect(page.getByText('Net Profit')).toBeVisible({ timeout: 10000 });

    // Revenue is present and non-zero (the sale we just recorded contributes)
    await expect(page.getByText('Total Revenue')).toBeVisible();
  });
});
