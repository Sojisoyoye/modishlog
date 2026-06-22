import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { ensureProduct, createOrder, deleteOrder, advanceOrderToStatus } from './helpers/data';

test.describe.configure({ mode: 'serial' });

let orderId: string;

test.beforeAll(async () => {
  await ensureTestUser();
  const product = await ensureProduct('E2E Sell Price Product');
  const order = await createOrder(product.id, { currency: 'NGN', quantity: 2, unitCost: '6000.00' });
  orderId = order.id;
  await advanceOrderToStatus(orderId, 'DELIVERED', { fxRateAtDelivery: '1580' });
});

test.afterAll(async () => {
  if (orderId) await deleteOrder(orderId).catch((e: Error) => {
    if (!/4\d\d/.test(e.message)) throw e;
  });
});

test.describe('Order line item sell price (sell_price_ngn)', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('sell column shows (catalog) label when sell_price_ngn is null', async ({ page }) => {
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
    await expect(page.getByText('(catalog)').first()).toBeVisible();
  });

  test('edit mode shows sell price input per line item', async ({ page }) => {
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
    await page.getByRole('button', { name: /edit/i }).click();
    await expect(page.getByTestId('sell-price-input').first()).toBeVisible();
  });

  test('entering a sell price saves and displays locked value', async ({ page }) => {
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();

    await page.getByRole('button', { name: /edit/i }).first().click();
    const sellInput = page.getByTestId('sell-price-input').first();
    await expect(sellInput).toBeVisible({ timeout: 5000 });

    await sellInput.fill('250000');
    await page.getByRole('button', { name: /save/i }).click();
    await expect(page.getByRole('button', { name: /edit/i })).toBeVisible({ timeout: 5000 });

    await expect(page.getByText('250,000').first()).toBeVisible();
  });
});
