import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import {
  ensureProduct,
  createOrder,
  deleteOrder,
  advanceOrderToStatus,
  recordPayment,
  createSale,
} from './helpers/data';

// ---------------------------------------------------------------------------
// Order detail: payment editing, revert-delivery, and the price-suggestion
// column — covers the delivered-order correction features (task 179/PR #335).
// ---------------------------------------------------------------------------

test.describe.configure({ mode: 'serial' });

test.describe('Payment editing', () => {
  let orderId: string;

  test.beforeAll(async () => {
    await ensureTestUser();
    const product = await ensureProduct('E2E Payment Edit Product');
    const order = await createOrder(product.id, { currency: 'NGN', quantity: 1, unitCost: '3000.00' });
    orderId = order.id;
    await recordPayment(orderId, { amount: '1000.00', currency: 'NGN' });
  });

  test.afterAll(async () => {
    if (orderId) await deleteOrder(orderId).catch((e: Error) => {
      if (!/4\d\d/.test(e.message)) throw e;
    });
  });

  test('editing a payment updates its displayed amount', async ({ page }) => {
    await loginViaUI(page);
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible({ timeout: 10_000 });

    // Enter order edit mode — payment edit/void controls only render then.
    await page.getByRole('button', { name: 'Edit' }).click();

    const paymentRow = page.getByTestId('payment-row').first();
    await expect(paymentRow).toBeVisible({ timeout: 10_000 });
    await paymentRow.getByTestId('edit-payment-btn').click();

    const amountInput = page.getByTestId('edit-payment-amount-input');
    await expect(amountInput).toBeVisible();
    await amountInput.fill('1500');
    await page.getByTestId('save-payment-btn').click();

    // Edit row closes and the payment list re-renders with the new amount.
    await expect(page.getByTestId('payment-edit-row')).not.toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('payment-row').first()).toContainText('1,500');
  });
});

test.describe('Revert delivery', () => {
  let untouchedOrderId: string;
  let soldFromOrderId: string;

  test.beforeAll(async () => {
    await ensureTestUser();
    const untouchedProduct = await ensureProduct('E2E Revert Untouched Product');
    const untouchedOrder = await createOrder(untouchedProduct.id, { currency: 'NGN', quantity: 5, unitCost: '2000.00' });
    untouchedOrderId = untouchedOrder.id;
    await advanceOrderToStatus(untouchedOrderId, 'DELIVERED', { fxRateAtDelivery: '1500' });

    const soldProduct = await ensureProduct('E2E Revert Sold Product');
    const soldOrder = await createOrder(soldProduct.id, { currency: 'NGN', quantity: 5, unitCost: '2000.00' });
    soldFromOrderId = soldOrder.id;
    await advanceOrderToStatus(soldFromOrderId, 'DELIVERED', { fxRateAtDelivery: '1500' });
    await createSale(soldProduct.id, { quantity: 1 });
  });

  test.afterAll(async () => {
    // Reverted order goes back to CLEARED, which deleteOrder can't cancel either — swallow 4xx.
    if (untouchedOrderId) await deleteOrder(untouchedOrderId).catch((e: Error) => {
      if (!/4\d\d/.test(e.message)) throw e;
    });
    if (soldFromOrderId) await deleteOrder(soldFromOrderId).catch((e: Error) => {
      if (!/4\d\d/.test(e.message)) throw e;
    });
  });

  test('reverting an untouched delivery moves the order back to CLEARED', async ({ page }) => {
    await loginViaUI(page);
    await page.goto(`/orders/${untouchedOrderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible({ timeout: 10_000 });

    await page.getByRole('button', { name: 'Revert to Cleared' }).click();

    const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Revert to Cleared' });
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    await dialog.getByRole('button', { name: 'Revert' }).click();

    await expect(page.locator('p').filter({ hasText: 'CLEARED' }).first()).toBeVisible({ timeout: 10_000 });
    // Terminal-status action must disappear once no longer DELIVERED.
    await expect(page.getByRole('button', { name: 'Revert to Cleared' })).not.toBeVisible();
  });

  test('reverting a delivery already sold from is rejected with a readable error', async ({ page }) => {
    await loginViaUI(page);
    await page.goto(`/orders/${soldFromOrderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible({ timeout: 10_000 });

    await page.getByRole('button', { name: 'Revert to Cleared' }).click();
    const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Revert to Cleared' });
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    await dialog.getByRole('button', { name: 'Revert' }).click();

    const toast = page.locator('.p-toast-message');
    await expect(toast).toBeVisible({ timeout: 10_000 });
    await expect(toast).toContainText(/sold from/i);
    // Status must NOT have changed.
    await expect(page.locator('p').filter({ hasText: 'DELIVERED' }).first()).toBeVisible();
  });
});

test.describe('Price suggestion column', () => {
  let orderId: string;

  test.beforeAll(async () => {
    await ensureTestUser();
    const product = await ensureProduct('E2E Suggestion Column Product');
    const order = await createOrder(product.id, { currency: 'USD', quantity: 10, unitCost: '10.00' });
    orderId = order.id;
  });

  test.afterAll(async () => {
    if (orderId) await deleteOrder(orderId).catch((e: Error) => {
      if (!/4\d\d/.test(e.message)) throw e;
    });
  });

  test('line items table shows a computed Suggested (₦) price', async ({ page }) => {
    await loginViaUI(page);
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible({ timeout: 10_000 });

    await expect(page.getByTestId('line-items-table').getByText('Suggested (₦)')).toBeVisible();
    const suggestionCell = page.getByTestId('suggested-price-cell').first();
    await expect(suggestionCell).toBeVisible({ timeout: 10_000 });
    // Cost is set on every seeded order, so a suggestion should always
    // compute — '—' would mean the fetch failed or margin_factor <= 0.
    await expect(suggestionCell).not.toHaveText('—');
  });
});
