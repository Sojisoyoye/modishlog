import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { ensureProduct } from './helpers/data';

// ---------------------------------------------------------------------------
// Settings — Margin Targets: completes the MarginTarget model (previously
// backend-only, zero UI) with a management page (task filed 2026-08-12).
// ---------------------------------------------------------------------------

test.describe.configure({ mode: 'serial' });

let productId: string;
let productName: string;

test.beforeAll(async () => {
  await ensureTestUser();
  productName = `E2E Margin Target Product ${Date.now()}`;
  const product = await ensureProduct(productName);
  productId = product.id;
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/settings');
});

test.describe('Settings — Margin Targets', () => {
  test('margin targets section is visible', async ({ page }) => {
    await expect(page.getByText('Margin Targets', { exact: true })).toBeVisible();
    await expect(page.getByTestId('margin-target-scope-select')).toBeVisible();
  });

  test('adding a product-level margin target shows it in the table, then deleting removes it', async ({ page }) => {
    await page.getByTestId('margin-target-scope-select').selectOption('product');
    await page.getByTestId('margin-target-product-select').selectOption({ label: productName });
    await page.getByTestId('margin-target-target-pct-input').fill('45');
    await page.getByTestId('margin-target-min-pct-input').fill('30');
    await page.getByTestId('margin-target-save-btn').click();

    await expect(page.getByText('Saved', { exact: true })).toBeVisible({ timeout: 10_000 });

    const row = page.getByTestId('margin-target-row').filter({ hasText: productName });
    await expect(row).toBeVisible({ timeout: 10_000 });
    await expect(row).toContainText('45');
    await expect(row).toContainText('30');

    await row.getByTestId('margin-target-delete-btn').click();
    const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Delete Margin Target' });
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    await dialog.getByRole('button', { name: 'Delete' }).click();

    await expect(page.getByTestId('margin-target-row').filter({ hasText: productName })).not.toBeVisible({ timeout: 10_000 });
  });

  test('save button stays disabled until a product/category and margins are set', async ({ page }) => {
    await page.getByTestId('margin-target-scope-select').selectOption('product');
    await expect(page.getByTestId('margin-target-save-btn')).toBeDisabled();

    await page.getByTestId('margin-target-product-select').selectOption({ label: productName });
    await expect(page.getByTestId('margin-target-save-btn')).toBeDisabled();

    await page.getByTestId('margin-target-target-pct-input').fill('40');
    await page.getByTestId('margin-target-min-pct-input').fill('20');
    await expect(page.getByTestId('margin-target-save-btn')).toBeEnabled();
  });
});
