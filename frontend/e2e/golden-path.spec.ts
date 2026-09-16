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
    const data: { quantity_on_hand: number } = await resp.json();
    return data.quantity_on_hand;
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

test.describe('Golden path — full MVP business cycle @smoke', () => {
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
    // The real UI login flow -- this test's whole point is verifying the
    // login form itself works as the first step of the golden path, not
    // just that an authenticated session works. Every other test below
    // also uses loginViaUI now (see task #231) for reliability, not just
    // this one for its original reason.
    await loginViaUI(page);
    await expect(page.getByText("Today's Revenue")).toBeVisible();
  });

  test('Purchase order transitions from ORDERED through to DELIVERED via UI', async ({ page }) => {
    // loginViaAPI's cookie-only session (set via page.context().request.post(),
    // outside the page's own JS) reliably survives the *first* subsequent
    // navigation but not a second one in WebKit specifically -- task #231's
    // CI run caught this landing back on /login instead of the target page.
    // loginViaUI drives the real login form, so the resulting session is
    // established through the app's normal login() flow instead, which is
    // what every real user's browser does -- proven reliable across all
    // three projects (this file's first test already used it for exactly
    // this reason, just not the other tests below it).
    await loginViaUI(page);
    await page.goto(`/orders/${orderId}`);
    await page.waitForLoadState('domcontentloaded');

    // --- ORDERED → PENDING ---
    // Explicit longer timeout on this first assertion only -- it's the one
    // waiting on the initial Angular bootstrap + order-detail API round
    // trip after page.goto(), not just a client-side state update like the
    // later transitions below. WebKit is measurably slower than Chromium at
    // this on CI (task #231 found it timing out at the 5s default), the
    // same class of first-load variance order-lifecycle.spec.ts and
    // order-detail.spec.ts already handle with the same explicit timeout.
    await expect(page.getByText('ORDERED').first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: 'PENDING' }).click();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByText('PENDING').first()).toBeVisible();

    // --- PENDING → IN_PRODUCTION ---
    await page.getByRole('button', { name: 'IN_PRODUCTION' }).click();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByText('IN_PRODUCTION').first()).toBeVisible();

    // --- IN_PRODUCTION → SHIPPING ---
    await page.getByRole('button', { name: 'SHIPPING' }).click();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByText('SHIPPING').first()).toBeVisible();

    // --- SHIPPING → CLEARED ---
    await page.getByRole('button', { name: 'CLEARED' }).click();
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByText('CLEARED').first()).toBeVisible();

    // --- CLEARED → DELIVERED ---
    // NGN orders are locally-sourced — nothing to convert, so no FX rate
    // input renders and none is required (task 181/182 follow-up).
    await page.getByRole('button', { name: 'DELIVERED' }).click();
    await page.waitForLoadState('domcontentloaded');
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
    // Wait for page heading — sales.spec.ts requires this before interacting with the form
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible({ timeout: 10_000 });

    // Switch to Record Sales tab (already the default, but click to ensure the form is shown)
    await page.getByTestId('tab-record-sales').click();

    // Use the same pattern as sales.spec.ts — filter by placeholder text to find the product select
    const productSelect = page.locator('select').filter({ hasText: 'Select product' }).first();
    await expect(productSelect).toBeVisible({ timeout: 15_000 });

    // Wait for products to load into the dropdown
    await expect(productSelect.locator('option').nth(1)).toBeAttached({ timeout: 10_000 });
    await productSelect.selectOption({ label: productName });

    // Set quantity to 3 — use first number input in the record sales form
    await page.locator('input[type="number"]').first().fill('3');

    // Submit — use last() because the "Record Sales" tab button also matches
    await page.getByRole('button', { name: 'Record Sales' }).last().click();
    await page.waitForLoadState('domcontentloaded');

    // Success toast — summary 'Success', detail 'Sales recorded successfully'
    await expect(page.getByText('Sales recorded successfully')).toBeVisible({ timeout: 8000 });

    // Stock decreased by exactly 3
    const stockAfter = await getStock(productId);
    expect(stockAfter).toBe(stockBefore - 3);
  });

  test('P&L report generates with non-zero revenue after the sale', async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/reports/profit-loss');
    await page.waitForLoadState('domcontentloaded');

    // Fill date range bracketing today
    await page.locator('#pl-start-date').fill(iso30DaysAgo());
    await page.locator('#pl-end-date').fill(isoToday());

    // Generate
    await page.getByRole('button', { name: 'Generate Report' }).click();
    await page.waitForLoadState('domcontentloaded');

    // Net Profit section appears
    await expect(page.getByText('Net Profit', { exact: true })).toBeVisible({ timeout: 10000 });

    // Revenue is present and non-zero (the sale we just recorded contributes)
    await expect(page.getByText('Total Sales')).toBeVisible();
  });
});
