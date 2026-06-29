import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

// ---------------------------------------------------------------------------
// CSV Export E2E Tests (task #71)
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Sales CSV Export', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/sales');
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible({ timeout: 15_000 });
    // Navigate to All Sales tab so the Export button is visible
    await page.getByTestId('tab-all-sales').click();
  });

  test('Export CSV button is visible on All Sales tab', async ({ page }) => {
    await expect(page.getByTestId('export-sales-csv')).toBeVisible();
  });

  test('clicking Export CSV initiates a file download', async ({ page }) => {
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByTestId('export-sales-csv').click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/sales.*\.csv/i);
  });
});

test.describe('Orders CSV Export', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/orders');
    await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible({ timeout: 15_000 });
  });

  test('Export CSV button is visible on Orders page', async ({ page }) => {
    await expect(page.getByTestId('export-orders-csv')).toBeVisible();
  });

  test('clicking Export CSV initiates a file download', async ({ page }) => {
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByTestId('export-orders-csv').click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/orders.*\.csv/i);
  });
});

test.describe('FX Rates CSV Export', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/fx');
    await expect(page.getByRole('heading', { name: 'FX Rates', exact: true })).toBeVisible({ timeout: 15_000 });
  });

  test('Export CSV button is visible on FX Rates page', async ({ page }) => {
    await expect(page.getByTestId('export-fx-csv')).toBeVisible();
  });

  test('clicking Export CSV initiates a file download', async ({ page }) => {
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByTestId('export-fx-csv').click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/fx.*\.csv/i);
  });
});
