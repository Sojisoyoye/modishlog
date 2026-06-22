import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { ensureProduct, createOrder, deleteOrder, advanceOrderToStatus } from './helpers/data';

test.describe.configure({ mode: 'serial' });

let deliveredOrderId: string;
let orderedOrderId: string;

test.beforeAll(async () => {
  await ensureTestUser();
  const product = await ensureProduct('E2E Lot Tracking Product');

  // One order advanced all the way to DELIVERED
  const delivered = await createOrder(product.id, { currency: 'NGN', quantity: 3, unitCost: '4000.00' });
  deliveredOrderId = delivered.id;
  await advanceOrderToStatus(deliveredOrderId, 'DELIVERED', { fxRateAtDelivery: '1580' });

  // One order left at ORDERED (not DELIVERED — used to assert In Stock is absent)
  const ordered = await createOrder(product.id, { currency: 'NGN', quantity: 1, unitCost: '4000.00' });
  orderedOrderId = ordered.id;
});

test.afterAll(async () => {
  const cleanup = async (id: string) =>
    deleteOrder(id).catch((e: Error) => { if (!/4\d\d/.test(e.message)) throw e; });
  if (deliveredOrderId) await cleanup(deliveredOrderId);
  if (orderedOrderId) await cleanup(orderedOrderId);
});

test.describe('Order lot inventory tracking', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('In Stock column is visible on DELIVERED orders', async ({ page }) => {
    await page.goto(`/orders/${deliveredOrderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
    await expect(page.getByText(/in stock/i).first()).toBeVisible();
  });

  test('In Stock column shows a value (number or dash) for delivered line items', async ({ page }) => {
    await page.goto(`/orders/${deliveredOrderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
    await expect(page.getByText(/in stock/i).first()).toBeVisible();
    // At least one In Stock cell must exist — value is a formatted integer or — for null lots
    const stockCells = page.locator('table td').filter({ hasText: /\d|—/ });
    await expect(stockCells.first()).toBeVisible();
  });

  test('In Stock column is NOT visible on non-delivered orders', async ({ page }) => {
    await page.goto(`/orders/${orderedOrderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
    await expect(page.getByText(/in stock/i)).not.toBeVisible();
  });
});
