import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
});

// ---------------------------------------------------------------------------
// Sales page
// ---------------------------------------------------------------------------
test('sales page: skeleton resolves and table is visible', async ({ page }) => {
  await page.goto('/sales');
  // Navigate to the "All transactions" tab (index 1) where the table lives
  await page.getByRole('tab', { name: /all/i }).click();
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
  await expect(page.getByRole('columnheader', { name: /product/i }).first()).toBeVisible();
});

// ---------------------------------------------------------------------------
// Orders page
// ---------------------------------------------------------------------------
test('orders page: skeleton resolves and table is visible', async ({ page }) => {
  await page.goto('/orders');
  await expect(page.locator('table').first()).toBeVisible({ timeout: 15000 });
  await expect(page.locator('.animate-pulse').first()).not.toBeVisible({ timeout: 10000 });
  await expect(page.getByRole('columnheader', { name: /order/i }).first()).toBeVisible();
});

// ---------------------------------------------------------------------------
// Inventory page
// ---------------------------------------------------------------------------
test('inventory page: skeleton resolves and table is visible', async ({ page }) => {
  await page.goto('/inventory');
  await expect(page.locator('table').first()).toBeVisible({ timeout: 15000 });
  await expect(page.locator('.animate-pulse').first()).not.toBeVisible({ timeout: 10000 });
  await expect(page.getByRole('columnheader', { name: /product/i }).first()).toBeVisible();
});
