import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { ensureProduct } from './helpers/data';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Order detail page', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/orders');
    await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible();
  });

  test('clicking an order row navigates to /orders/:id', async ({ page }) => {
    // Click the first order row in the table (if any exist)
    const firstRow = page.locator('table tbody tr').first();
    const rowCount = await page.locator('table tbody tr').count();
    if (rowCount === 0 || (await firstRow.textContent())?.includes('No orders')) {
      test.skip();
      return;
    }
    const orderNumber = await firstRow.locator('td').first().textContent();
    await firstRow.click();
    await expect(page).toHaveURL(/\/orders\//);
    await expect(page.getByText(orderNumber!.trim())).toBeVisible();
  });

  test('detail page shows order header fields', async ({ page }) => {
    const firstRow = page.locator('table tbody tr').first();
    const rowCount = await page.locator('table tbody tr').count();
    if (rowCount === 0 || (await firstRow.textContent())?.includes('No orders')) {
      test.skip();
      return;
    }
    await firstRow.click();
    await expect(page).toHaveURL(/\/orders\//);
    await expect(page.getByText('Supplier')).toBeVisible();
    await expect(page.getByText('Status')).toBeVisible();
  });

  test('detail page has a Back to Orders link', async ({ page }) => {
    const firstRow = page.locator('table tbody tr').first();
    const rowCount = await page.locator('table tbody tr').count();
    if (rowCount === 0 || (await firstRow.textContent())?.includes('No orders')) {
      test.skip();
      return;
    }
    await firstRow.click();
    await expect(page).toHaveURL(/\/orders\//);
    const backLink = page.getByRole('link', { name: /back/i }).or(
      page.getByRole('button', { name: /back/i })
    );
    await expect(backLink).toBeVisible();
    await backLink.click();
    await expect(page).toHaveURL('/orders');
  });

  test('detail page shows line items table', async ({ page }) => {
    const firstRow = page.locator('table tbody tr').first();
    const rowCount = await page.locator('table tbody tr').count();
    if (rowCount === 0 || (await firstRow.textContent())?.includes('No orders')) {
      test.skip();
      return;
    }
    await firstRow.click();
    await expect(page).toHaveURL(/\/orders\//);
    await expect(page.getByTestId('line-items-table')).toBeVisible();
  });

  test('direct URL navigation to /orders/:id works', async ({ page }) => {
    // First get an order id via API
    const resp = await page.request.get('/api/orders');
    const data = await resp.json();
    if (!data.items || data.items.length === 0) {
      test.skip();
      return;
    }
    const id = data.items[0].id;
    await page.goto(`/orders/${id}`);
    await expect(page.getByText(data.items[0].order_number)).toBeVisible();
  });
});
