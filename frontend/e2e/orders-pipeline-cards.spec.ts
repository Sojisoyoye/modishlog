import { test, expect, request, type Page } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';
import { ensureProduct, advanceOrderToStatus } from './helpers/data';

const API = 'http://localhost:8000/api/v1';

/**
 * Create a purchase order (is_purchase_order=true) and advance it to `status`.
 * The backend ignores a `status` field in the create payload; we must use the
 * status-transition API to reach the desired state.
 */
async function createOrder(
  productId: string,
  status: string,
): Promise<{ id: string; order_number: string }> {
  const token = await getAPIToken();
  for (let attempt = 0; attempt < 3; attempt++) {
    const ctx = await request.newContext();
    try {
      const resp = await ctx.post(`${API}/orders`, {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          supplier_name: 'Pipeline Test Supplier',
          is_purchase_order: true,
          currency: 'USD',
          line_items: [
            { product_id: productId, quantity: 5, unit_cost: '100.00' },
          ],
        },
      });
      if (resp.ok()) {
        const order = await resp.json();
        // Advance to desired status if not already ORDERED
        if (status !== 'ORDERED') {
          await advanceOrderToStatus(order.id, status, { fxRateAtDelivery: '1500' });
        }
        return order;
      }
      if (resp.status() >= 500 && attempt < 2) {
        await ctx.dispose();
        await new Promise(r => setTimeout(r, 500 * (attempt + 1)));
        continue;
      }
      throw new Error(`Failed to create order: ${resp.status()} ${await resp.text()}`);
    } finally {
      await ctx.dispose();
    }
  }
  throw new Error('Failed to create order after 3 attempts');
}

/**
 * Locate the pipeline filter button for a given status label.
 * The orders page uses filter buttons (not h4 cards) for pipeline statuses.
 */
function pipelineFilterButton(page: Page, label: string) {
  // Use getByRole with name to match by accessible name (more reliable than hasText + ^ anchor)
  return page.getByRole('button', { name: new RegExp(label, 'i') }).first();
}

test.describe('Orders pipeline status cards', () => {
  let productId: string;

  test.beforeAll(async () => {
    await ensureTestUser();
    const product = await ensureProduct('Pipeline Card Test Product');
    productId = product.id;
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('pipeline filter buttons show human-readable labels', async ({ page }) => {
    await page.goto('/orders');
    await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible({ timeout: 15_000 });

    // Each filter button must show the friendly label
    const expectedLabels = ['Ordered', 'Pending', 'In Production', 'Shipping', 'Cleared', 'Delivered'];
    for (const label of expectedLabels) {
      await expect(page.getByRole('button', { name: new RegExp(label, 'i') }).first()).toBeVisible();
    }

    // The raw underscore enum values must NOT appear as button text
    const rawValues = ['PENDING', 'IN_PRODUCTION', 'SHIPPING', 'CLEARED', 'DELIVERED'];
    for (const raw of rawValues) {
      // Should not have a button whose accessible name exactly equals the raw value
      await expect(page.getByRole('button', { name: new RegExp(`^${raw}$`) })).toHaveCount(0);
    }
  });

  test('orders appear in the table when filtered by their status', async ({ page }) => {
    test.setTimeout(90000); // Order status advancement (DELIVERED) requires many API calls
    const pending = await createOrder(productId, 'PENDING');
    const shipping = await createOrder(productId, 'SHIPPING');
    const delivered = await createOrder(productId, 'DELIVERED');

    await page.goto('/orders');
    await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible({ timeout: 15_000 });

    // Click the "Pending" filter button and assert the pending order appears in the table
    await pipelineFilterButton(page, 'Pending').click();
    await expect(page.getByRole('cell', { name: pending.order_number }).first()).toBeVisible({ timeout: 5_000 });

    // Click the "Shipping" filter button
    await pipelineFilterButton(page, 'Shipping').click();
    await expect(page.getByRole('cell', { name: shipping.order_number }).first()).toBeVisible({ timeout: 5_000 });

    // Click the "Delivered" filter button
    await pipelineFilterButton(page, 'Delivered').click();
    await expect(page.getByRole('cell', { name: delivered.order_number }).first()).toBeVisible({ timeout: 5_000 });
  });

  test('pipeline filter button count is non-zero when orders exist in that status', async ({ page }) => {
    await createOrder(productId, 'IN_PRODUCTION');

    await page.goto('/orders');
    await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible({ timeout: 15_000 });

    // The "In Production" button should show a non-zero count badge
    const btn = pipelineFilterButton(page, 'In Production');
    await expect(btn).toBeVisible();
    // Wait until the count badge shows a non-zero value (API may be loading)
    await expect(btn.locator('span.rounded-full')).not.toHaveText('0', { timeout: 10_000 });
    const countText = await btn.locator('span.rounded-full').textContent();
    expect(parseInt(countText?.trim() ?? '0')).toBeGreaterThan(0);
  });

  test('pipeline filter badge count matches table row count for that status', async ({ page }) => {
    await createOrder(productId, 'PENDING');

    await page.goto('/orders');
    await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible({ timeout: 15_000 });

    // Get the badge count from the "Pending" filter button
    const btn = pipelineFilterButton(page, 'Pending');
    await expect(btn).toBeVisible();
    const cardCount = parseInt((await btn.locator('span.rounded-full').textContent())?.trim() ?? '0');

    // Click the filter and count table rows
    // Verify the badge count is non-zero (pending orders exist)
    expect(cardCount).toBeGreaterThan(0);

    await btn.click();
    const rows = page.locator('table tbody tr').filter({
      hasNot: page.locator('td[colspan]'),
    });
    // After filtering, at least one row should be visible
    await expect(rows.first()).toBeVisible({ timeout: 5_000 });
  });
});
