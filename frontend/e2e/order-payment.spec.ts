import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';
import { ensureProduct, createOrder, deleteOrder, advanceOrderToStatus } from './helpers/data';

const API = 'http://localhost:8000/api/v1';

test.describe.configure({ mode: 'serial' });

const orderCurrency = 'NGN';

let orderId: string;

test.beforeAll(async () => {
  await ensureTestUser();
  const product = await ensureProduct('E2E Payment Product');
  const order = await createOrder(product.id, { currency: orderCurrency, quantity: 2, unitCost: '5000.00' });
  orderId = order.id;
  await advanceOrderToStatus(orderId, 'DELIVERED', { fxRateAtDelivery: '1580' });
});

test.afterAll(async () => {
  // DELIVERED orders cannot be cancelled — swallow 4xx only
  if (orderId) await deleteOrder(orderId).catch((e: Error) => {
    if (!/4\d\d/.test(e.message)) throw e;
  });
});

test.describe('Order payment recording', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('payment section is visible on order detail', async ({ page }) => {
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
    await expect(page.getByTestId('payment-section')).toBeVisible();
  });

  test('edit mode reveals record-payment form', async ({ page }) => {
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
    await page.getByRole('button', { name: /edit/i }).click();
    await expect(page.getByTestId('payment-record-form')).toBeVisible();
    await expect(page.getByTestId('payment-amount-input')).toBeVisible();
    await expect(page.getByTestId('payment-method-select')).toBeVisible();
    await expect(page.getByTestId('payment-date-input')).toBeVisible();
  });

  test('recording a payment adds it to the list and updates summary', async ({ page }) => {
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();

    // Void any existing payments so balance > 0
    const token = await getAPIToken();
    const ctx = await request.newContext();
    try {
      const beforeResp = await ctx.get(`${API}/orders/${orderId}/payments`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const existing: { id: string; status: string }[] = await beforeResp.json();
      for (const p of existing.filter((p) => p.status !== 'VOIDED')) {
        await ctx.delete(`${API}/orders/${orderId}/payments/${p.id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
      }
    } finally {
      await ctx.dispose();
    }

    await page.reload();
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();

    const paidBefore = page.getByTestId('total-paid-value');
    const paidTextBefore = await paidBefore.textContent().catch(() => '0');

    await page.getByRole('button', { name: /edit/i }).click();
    await page.getByTestId('payment-amount-input').fill('100');
    await page.getByTestId('payment-date-input').fill('2026-06-11');
    await page.getByTestId('record-payment-btn').click();

    await expect(page.getByTestId('payment-row').first()).toBeVisible();
    await expect(page.getByTestId('total-paid-value')).not.toHaveText(paidTextBefore ?? '');
  });

  test('void button marks payment as voided', async ({ page }) => {
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();

    // Ensure at least one COMPLETED payment exists via API
    const token = await getAPIToken();
    const ctx = await request.newContext();
    try {
      await ctx.post(`${API}/orders/${orderId}/payments`, {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          amount: 50,
          currency: orderCurrency,
          payment_date: '2026-06-11',
          payment_method: 'CASH',
        },
      });
    } finally {
      await ctx.dispose();
    }

    await page.reload();
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();

    await page.getByRole('button', { name: /edit/i }).click();
    await expect(page.getByTestId('void-payment-btn').first()).toBeVisible();
    await page.getByTestId('void-payment-btn').first().click();

    // At least one payment row must show voided status after the operation
    await expect(page.getByTestId('payment-row').filter({ hasText: /void/i }).first()).toBeVisible({ timeout: 5_000 });
  });
});
