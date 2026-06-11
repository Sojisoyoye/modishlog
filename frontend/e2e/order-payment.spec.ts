import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Order payment recording', () => {
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

  test('payment section is visible on order detail', async ({ page }) => {
    const order = await goToFirstOrder(page);
    if (!order) { test.skip(); return; }
    await expect(page.getByTestId('payment-section')).toBeVisible();
  });

  test('edit mode reveals record-payment form', async ({ page }) => {
    const order = await goToFirstOrder(page);
    if (!order) { test.skip(); return; }
    await page.getByRole('button', { name: /edit/i }).click();
    await expect(page.getByTestId('payment-record-form')).toBeVisible();
    await expect(page.getByTestId('payment-amount-input')).toBeVisible();
    await expect(page.getByTestId('payment-method-select')).toBeVisible();
    await expect(page.getByTestId('payment-date-input')).toBeVisible();
  });

  test('recording a payment adds it to the list and updates summary', async ({ page }) => {
    const order = await goToFirstOrder(page);
    if (!order) { test.skip(); return; }

    // Void any existing payments so balance > 0
    const beforeResp = await page.request.get(`/api/orders/${order.id}/payments`);
    const existing: { id: string; status: string }[] = await beforeResp.json();
    for (const p of existing.filter((p) => p.status !== 'VOIDED')) {
      await page.request.delete(`/api/orders/${order.id}/payments/${p.id}`);
    }
    await page.reload();
    await expect(page.getByText(order.order_number)).toBeVisible();

    const paidBefore = page.getByTestId('total-paid-value');
    const paidTextBefore = await paidBefore.textContent().catch(() => '0');

    await page.getByRole('button', { name: /edit/i }).click();
    await page.getByTestId('payment-amount-input').fill('100');
    await page.getByTestId('payment-date-input').fill('2026-06-11');
    await page.getByTestId('record-payment-btn').click();

    // Payment row appears
    await expect(page.getByTestId('payment-row').first()).toBeVisible();
    // Paid total updated
    await expect(page.getByTestId('total-paid-value')).not.toHaveText(paidTextBefore ?? '');
  });

  test('void button marks payment as voided', async ({ page }) => {
    const order = await goToFirstOrder(page);
    if (!order) { test.skip(); return; }

    // Ensure at least one COMPLETED payment exists
    await page.request.post(`/api/orders/${order.id}/payments`, {
      data: {
        amount: 50,
        currency: order.currency ?? 'USD',
        payment_date: '2026-06-11',
        payment_method: 'CASH',
      },
    });
    await page.reload();
    await expect(page.getByText(order.order_number)).toBeVisible();

    await page.getByRole('button', { name: /edit/i }).click();
    await expect(page.getByTestId('void-payment-btn').first()).toBeVisible();
    await page.getByTestId('void-payment-btn').first().click();

    // The row should be marked voided (class or text change)
    await expect(page.getByTestId('payment-row').first()).toContainText(/void/i);
  });
});
