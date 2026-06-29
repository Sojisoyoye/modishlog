import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';
import { ensureProduct, createOrder, deleteOrder } from './helpers/data';

const API = 'http://localhost:8000/api/v1';

test.describe.configure({ mode: 'serial' });

let orderId: string;
let orderNumber: string;

test.beforeAll(async () => {
  await ensureTestUser();
  const product = await ensureProduct('E2E Detail Product');
  const order = await createOrder(product.id, { currency: 'NGN', quantity: 1, unitCost: '3000.00' });
  orderId = order.id;
  // Fetch the generated order_number for assertions
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.get(`${API}/orders/${orderId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    orderNumber = (await resp.json()).order_number;
  } finally {
    await ctx.dispose();
  }
});

test.afterAll(async () => {
  if (orderId) await deleteOrder(orderId).catch((e: Error) => {
    if (!/4\d\d/.test(e.message)) throw e;
  });
});

test.describe('Order detail page', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('clicking an order row navigates to /orders/:id', async ({ page }) => {
    await page.goto('/orders');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible({ timeout: 10_000 });
    // Wait for orders to load, then find the seeded order row
    const orderRow = page.locator('table tbody tr').filter({ hasText: orderNumber });
    await expect(orderRow).toBeVisible({ timeout: 10_000 });
    await orderRow.click();
    await expect(page).toHaveURL(/\/orders\//);
    // Use heading to avoid strict-mode violation (PO number appears in both span and h2)
    await expect(page.getByRole('heading', { name: orderNumber })).toBeVisible();
  });

  test('detail page shows order header fields', async ({ page }) => {
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
    // Use exact:true to avoid matching 'Suppliers' nav link or 'E2E Test Supplier' text
    await expect(page.getByText('Supplier', { exact: true })).toBeVisible();
    await expect(page.getByText('Status', { exact: true })).toBeVisible();
  });

  test('detail page has a Back to Orders link', async ({ page }) => {
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
    const backLink = page.getByRole('link', { name: /back/i }).or(
      page.getByRole('button', { name: /back/i })
    );
    await expect(backLink).toBeVisible();
    await backLink.click();
    await expect(page).toHaveURL('/orders');
  });

  test('detail page shows line items table', async ({ page }) => {
    await page.goto(`/orders/${orderId}`);
    await expect(page.getByRole('heading', { name: /PO-/ })).toBeVisible();
    await expect(page.getByTestId('line-items-table')).toBeVisible();
  });

  test('direct URL navigation to /orders/:id works', async ({ page }) => {
    await page.goto(`/orders/${orderId}`);
    // Use heading to avoid strict-mode: order number appears in both span and h2
    await expect(page.getByRole('heading', { name: orderNumber })).toBeVisible();
  });
});
