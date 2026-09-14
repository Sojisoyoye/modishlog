import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaAPI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaAPI(page);
});

// ---------------------------------------------------------------------------
// Sales page
// ---------------------------------------------------------------------------
test('sales page: skeleton resolves and table is visible', async ({ page }) => {
  await page.goto('/sales');
  // Navigate to the "All Sales" tab where the table lives. It's a plain
  // <button> (aria-selected alone doesn't give it role="tab"), so
  // getByRole('tab', ...) never matches -- use the dedicated testid.
  await page.getByTestId('tab-all-sales').click();
  // Skeleton or table — either is correct immediately after nav; wait for table
  await expect(page.locator('table').first()).toBeVisible({ timeout: 15000 });
  // No skeleton rows should remain once loading is done
  await expect(page.locator('.animate-pulse').first()).not.toBeVisible({ timeout: 10000 });
  // Column header confirms the right table is showing
  await expect(page.getByRole('columnheader', { name: /date/i }).first()).toBeVisible();
});

// ---------------------------------------------------------------------------
// Products page
// ---------------------------------------------------------------------------
test('products page: skeleton resolves and table is visible', async ({ page }) => {
  await page.goto('/products');
  await expect(page.locator('table').first()).toBeVisible({ timeout: 15000 });
  await expect(page.locator('.animate-pulse').first()).not.toBeVisible({ timeout: 10000 });
  // "Actions" is the only unconditional <th> — all other columns are gated by visibleCols()
  await expect(page.getByRole('columnheader', { name: 'Actions' }).first()).toBeVisible();
});

// ---------------------------------------------------------------------------
// Orders page
// ---------------------------------------------------------------------------
test('orders page: skeleton resolves and table is visible', async ({ page }) => {
  await page.goto('/orders');
  await expect(page.locator('table').first()).toBeVisible({ timeout: 15000 });
  await expect(page.locator('.animate-pulse').first()).not.toBeVisible({ timeout: 10000 });
  // "Order #" is the first unconditional column header in the orders table
  await expect(page.getByRole('columnheader', { name: 'Order #' }).first()).toBeVisible();
});

// ---------------------------------------------------------------------------
// Inventory page
// ---------------------------------------------------------------------------
test('inventory page: skeleton resolves and table is visible', async ({ page }) => {
  await page.goto('/inventory');
  await expect(page.locator('table').first()).toBeVisible({ timeout: 15000 });
  await expect(page.locator('.animate-pulse').first()).not.toBeVisible({ timeout: 10000 });
  // "Stock" is a stable, unconditional header unique to the inventory table
  await expect(page.getByRole('columnheader', { name: 'Stock' }).first()).toBeVisible();
});

// ---------------------------------------------------------------------------
// Sales page aria-live
// ---------------------------------------------------------------------------
test('sales transactions table has aria-live region', async ({ page }) => {
  await page.goto('/sales');
  await expect(page.locator('[aria-live="polite"]').first()).toBeAttached({ timeout: 5000 });
});
