import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';

const API = 'http://localhost:8000/api/v1';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Order lot inventory tracking', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  async function findDeliveredOrder() {
    const token = await getAPIToken();
    const ctx = await request.newContext();
    try {
      const resp = await ctx.get(`${API}/orders?page_size=50`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await resp.json();
      return (data.items ?? []).find((o: { status: string }) => o.status === 'DELIVERED') ?? null;
    } finally {
      await ctx.dispose();
    }
  }

  async function findPendingOrder() {
    const token = await getAPIToken();
    const ctx = await request.newContext();
    try {
      const resp = await ctx.get(`${API}/orders?page_size=50`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await resp.json();
      return (data.items ?? []).find((o: { status: string }) => o.status === 'PENDING') ?? null;
    } finally {
      await ctx.dispose();
    }
  }

  test('In Stock column is visible on DELIVERED orders', async ({ page }) => {
    const order = await findDeliveredOrder();
    if (!order) { test.skip(); return; }
    await page.goto(`/orders/${order.id}`);
    await expect(page.getByText(/in stock/i).first()).toBeVisible();
  });

  test('In Stock column shows a value (number or dash) for delivered line items', async ({ page }) => {
    const order = await findDeliveredOrder();
    if (!order) { test.skip(); return; }
    await page.goto(`/orders/${order.id}`);
    // In Stock column header must be present
    await expect(page.getByText(/in stock/i).first()).toBeVisible();
    // At least one In Stock cell must exist — value is a formatted integer or — for null lots
    const stockCells = page.locator('table td').filter({ hasText: /\d|—/ });
    await expect(stockCells.first()).toBeVisible();
  });

  test('In Stock column is NOT visible on non-delivered orders', async ({ page }) => {
    const pending = await findPendingOrder();
    if (!pending) { test.skip(); return; }
    await page.goto(`/orders/${pending.id}`);
    await expect(page.getByText(/in stock/i)).not.toBeVisible();
  });
});
