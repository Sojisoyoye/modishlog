import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { ensureProduct, createOrder, deleteOrder } from './helpers/data';

// ---------------------------------------------------------------------------
// Order Status Lifecycle E2E Tests
// Drives an order through every status via UI buttons and asserts badge updates.
// ORDERED → PENDING → IN_PRODUCTION → SHIPPING → CLEARED → DELIVERED
// ---------------------------------------------------------------------------

test.describe.configure({ mode: 'serial' });

let orderId: string;

test.beforeAll(async () => {
  await ensureTestUser();
  const product = await ensureProduct('E2E Lifecycle Product');
  const order = await createOrder(product.id, { currency: 'NGN', quantity: 2, unitCost: '5000.00' });
  orderId = order.id;
});

test.afterAll(async () => {
  // DELIVERED orders cannot be cancelled; swallow only 4xx responses.
  if (orderId) {
    await deleteOrder(orderId).catch((e: Error) => {
      if (!/4\d\d/.test(e.message)) throw e;
    });
  }
});

test('ORDERED → PENDING: advance status and assert badge updates', async ({ page }) => {
  await loginViaUI(page);
  await page.goto(`/orders/${orderId}`);
  await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
  await page.waitForLoadState('networkidle');

  await expect(page.locator('span').filter({ hasText: /^ORDERED$/ }).first()).toBeVisible();

  await page.getByRole('button', { name: 'PENDING' }).click();
  await page.screenshot({ path: 'e2e-screenshots/lifecycle-01-pending.png' });

  await expect(page.locator('span').filter({ hasText: /^PENDING$/ }).first()).toBeVisible();
});

test('PENDING → IN_PRODUCTION: advance status and assert badge updates', async ({ page }) => {
  await loginViaUI(page);
  await page.goto(`/orders/${orderId}`);
  await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
  await page.waitForLoadState('networkidle');

  await expect(page.locator('span').filter({ hasText: /^PENDING$/ }).first()).toBeVisible();

  await page.getByRole('button', { name: 'IN_PRODUCTION' }).click();
  await page.screenshot({ path: 'e2e-screenshots/lifecycle-02-in-production.png' });

  await expect(page.locator('span').filter({ hasText: /^IN_PRODUCTION$/ }).first()).toBeVisible();
});

test('IN_PRODUCTION → SHIPPING: advance status and assert badge updates', async ({ page }) => {
  await loginViaUI(page);
  await page.goto(`/orders/${orderId}`);
  await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
  await page.waitForLoadState('networkidle');

  await expect(page.locator('span').filter({ hasText: /^IN_PRODUCTION$/ }).first()).toBeVisible();

  await page.getByRole('button', { name: 'SHIPPING' }).click();
  await page.screenshot({ path: 'e2e-screenshots/lifecycle-03-shipping.png' });

  await expect(page.locator('span').filter({ hasText: /^SHIPPING$/ }).first()).toBeVisible();
});

test('SHIPPING → CLEARED: advance status and assert badge updates', async ({ page }) => {
  await loginViaUI(page);
  await page.goto(`/orders/${orderId}`);
  await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
  await page.waitForLoadState('networkidle');

  await expect(page.locator('span').filter({ hasText: /^SHIPPING$/ }).first()).toBeVisible();

  await page.getByRole('button', { name: 'CLEARED' }).click();
  await page.screenshot({ path: 'e2e-screenshots/lifecycle-04-cleared.png' });

  await expect(page.locator('span').filter({ hasText: /^CLEARED$/ }).first()).toBeVisible();
});

test('CLEARED → DELIVERED: fill FX rate, advance status, assert badge and In Stock column', async ({ page }) => {
  await loginViaUI(page);
  await page.goto(`/orders/${orderId}`);
  await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
  await page.waitForLoadState('networkidle');

  await expect(page.locator('span').filter({ hasText: /^CLEARED$/ }).first()).toBeVisible();

  // DELIVERED transition requires FX rate at delivery
  const fxInput = page.locator('input[placeholder="e.g. 1600"]');
  await expect(fxInput).toBeVisible();
  await fxInput.fill('1580');

  await page.getByRole('button', { name: 'DELIVERED' }).click();
  await page.screenshot({ path: 'e2e-screenshots/lifecycle-05-delivered.png' });

  await expect(page.locator('span').filter({ hasText: /^DELIVERED$/ }).first()).toBeVisible();

  // After DELIVERED the line items table gains an 'In Stock' column header
  await expect(page.getByTestId('line-items-table').getByText('In Stock')).toBeVisible();
});
