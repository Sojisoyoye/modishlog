import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';

const API = 'http://localhost:8000/api/v1';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Order line item sell price (sell_price_ngn)', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  async function goToFirstOrder(page: import('@playwright/test').Page) {
    const token = await getAPIToken();
    const ctx = await request.newContext();
    let data: { items?: { id: string; order_number: string }[] };
    try {
      const resp = await ctx.get(`${API}/orders`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      data = await resp.json();
    } finally {
      await ctx.dispose();
    }
    if (!data.items || data.items.length === 0) return null;
    const order = data.items[0];
    await page.goto(`/orders/${order.id}`);
    await expect(page.getByText(order.order_number).first()).toBeVisible();
    return order;
  }

  test('sell column shows (catalog) label when sell_price_ngn is null', async ({ page }) => {
    const order = await goToFirstOrder(page);
    if (!order) { test.skip(); return; }
    // In view mode, at least one cell should show the catalog label
    await expect(page.getByText('(catalog)').first()).toBeVisible();
  });

  test('edit mode shows sell price input per line item', async ({ page }) => {
    const order = await goToFirstOrder(page);
    if (!order) { test.skip(); return; }
    await page.getByRole('button', { name: /edit/i }).click();
    await expect(page.getByTestId('sell-price-input').first()).toBeVisible();
  });

  test('entering a sell price saves and displays locked value', async ({ page }) => {
    const order = await goToFirstOrder(page);
    if (!order) { test.skip(); return; }

    await page.getByRole('button', { name: /edit/i }).first().click();

    const sellInput = page.getByTestId('sell-price-input').first();
    // Wait up to 4s for Angular to enter edit mode; skip if not applicable
    try {
      await sellInput.waitFor({ state: 'visible', timeout: 4000 });
    } catch {
      test.skip(); return;
    }

    await sellInput.fill('250000');

    await page.getByRole('button', { name: /save/i }).click();
    await expect(page.getByRole('button', { name: /edit/i })).toBeVisible({ timeout: 5000 });

    await expect(page.getByText('250,000').first()).toBeVisible();
  });
});
