import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Order lot inventory tracking', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  async function findDeliveredOrder(page: import('@playwright/test').Page) {
    const resp = await page.request.get('/api/orders?page_size=50');
    const data = await resp.json();
    return (data.items ?? []).find((o: { status: string }) => o.status === 'DELIVERED') ?? null;
  }

  test('In Stock column is visible on DELIVERED orders', async ({ page }) => {
    const order = await findDeliveredOrder(page);
    if (!order) { test.skip(); return; }
    await page.goto(`/orders/${order.id}`);
    await expect(page.getByText(/in stock/i).first()).toBeVisible();
  });

  test('In Stock column shows numeric quantity for delivered line items', async ({ page }) => {
    const order = await findDeliveredOrder(page);
    if (!order) { test.skip(); return; }
    await page.goto(`/orders/${order.id}`);
    // At least one cell in the In Stock column should show a number
    const stockCells = page.locator('table td').filter({ hasText: /^\d+$/ });
    await expect(stockCells.first()).toBeVisible();
  });

  test('In Stock column is NOT visible on non-delivered orders', async ({ page }) => {
    const resp = await page.request.get('/api/orders?page_size=50');
    const data = await resp.json();
    const pending = (data.items ?? []).find((o: { status: string }) => o.status === 'PENDING');
    if (!pending) { test.skip(); return; }
    await page.goto(`/orders/${pending.id}`);
    await expect(page.getByText(/in stock/i)).not.toBeVisible();
  });
});
