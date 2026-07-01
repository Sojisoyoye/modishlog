import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { ensureProduct, addStock, createSale } from './helpers/data';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/returns');
  await expect(page.getByRole('heading', { name: 'Returns' })).toBeVisible({ timeout: 15000 });
});

test('returns page loads with tabs', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Returns' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sell Returns' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Purchase Returns' })).toBeVisible();
});

test('sell returns tab shows list', async ({ page }) => {
  await page.getByRole('button', { name: 'Sell Returns' }).click();
  await expect(page.getByRole('table').first()).toBeVisible({ timeout: 10000 });
});

test('purchase returns tab shows list', async ({ page }) => {
  await page.getByRole('button', { name: 'Purchase Returns' }).click();
  await expect(page.getByRole('table').last()).toBeVisible({ timeout: 10000 });
});

test('create sell return', async ({ page }) => {
  const product = await ensureProduct('E2E Returns Product');
  await addStock(product.id, 10);
  const sale = await createSale(product.id, { quantity: 1, unitPrice: '5000.00' });

  await page.getByRole('button', { name: 'Log Return' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();

  // Wait for sales to load then search by the new sale's ID prefix
  await page.getByPlaceholder('Search by date, customer or ID…').waitFor({ timeout: 5000 });
  await page.getByPlaceholder('Search by date, customer or ID…').fill(sale.id.slice(0, 8));
  const listItems = page.locator('ul li button');
  await listItems.first().waitFor({ timeout: 5000 });
  await listItems.first().click();

  await page.getByLabel('Total Amount').fill('1000');
  await page.getByRole('button', { name: 'Save Return' }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden', timeout: 10000 });

  // New row should be prepended to the sell returns table
  await expect(page.getByRole('table').first().locator('tbody tr').first()).not.toHaveText(
    'No sell returns found.',
    { timeout: 5000 },
  );
});
