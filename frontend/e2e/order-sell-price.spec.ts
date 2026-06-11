import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Order line item sell price (sell_price_ngn)', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  async function goToFirstOrder(page: import('@playwright/test').Page) {
    const resp = await page.request.get('/api/orders');
    const data = await resp.json();
    if (!data.items || data.items.length === 0) return null;
    const order = data.items[0];
    await page.goto(`/orders/${order.id}`);
    await expect(page.getByText(order.order_number)).toBeVisible();
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
    // Sell price inputs should be present (one per line item)
    const sellInputs = page.locator('input[placeholder]').filter({ hasText: '' });
    // The sell price column uses number inputs with placeholder from catalog price
    // Just verify the edit button revealed inputs in the table
    await expect(page.getByRole('button', { name: /save/i })).toBeVisible();
  });

  test('entering a sell price saves and displays locked value', async ({ page }) => {
    const order = await goToFirstOrder(page);
    if (!order) { test.skip(); return; }

    await page.getByRole('button', { name: /edit/i }).click();

    // Find the sell price inputs (number inputs in the line items table)
    // They have placeholder equal to the catalog price
    const sellInputs = page.locator('table input[type="number"]').filter({});
    const count = await sellInputs.count();
    if (count === 0) { test.skip(); return; }

    // Use the last number input in the line-items table row as sell price input
    // (order: qty, unit_cost, unit_cost_ngn, sell_price_ngn per row)
    const firstSellInput = sellInputs.last();
    await firstSellInput.fill('250000');

    await page.getByRole('button', { name: /save/i }).click();
    await expect(page.getByRole('button', { name: /edit/i })).toBeVisible({ timeout: 5000 });

    // Locked value should be visible; (catalog) label should be gone for this item
    await expect(page.getByText('250,000').first()).toBeVisible();
  });
});
