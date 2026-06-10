import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/reports');
  await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
});

test('shows Reports heading and three report cards', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
  await expect(page.getByText('Profit & Loss')).toBeVisible();
  await expect(page.getByText('Stock Report')).toBeVisible();
  await expect(page.getByText('Purchase & Sale')).toBeVisible();
});

test('navigates to profit/loss report page', async ({ page }) => {
  await page.getByText('Profit & Loss').click();
  await expect(page).toHaveURL('/reports/profit-loss');
  await expect(page.getByRole('heading', { name: 'Profit & Loss Report' })).toBeVisible();
});

test('navigates to stock report page', async ({ page }) => {
  await page.getByText('Stock Report').click();
  await expect(page).toHaveURL('/reports/stock');
  await expect(page.getByRole('heading', { name: 'Stock Report' })).toBeVisible();
});

test('navigates to purchase & sale report page', async ({ page }) => {
  await page.getByText('Purchase & Sale').click();
  await expect(page).toHaveURL('/reports/purchase-sale');
  await expect(page.getByRole('heading', { name: 'Purchase & Sale Report' })).toBeVisible();
});

test('profit/loss page has date filters and generate button', async ({ page }) => {
  await page.goto('/reports/profit-loss');
  await expect(page.locator('input[type="date"]').first()).toBeVisible();
  await expect(page.locator('input[type="date"]').nth(1)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Generate Report' })).toBeVisible();
});

test('stock report page has generate button', async ({ page }) => {
  await page.goto('/reports/stock');
  await expect(page.getByRole('button', { name: 'Generate Report' })).toBeVisible();
});
