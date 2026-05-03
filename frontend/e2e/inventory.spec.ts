import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI, E2E_EMAIL, E2E_PASSWORD } from './helpers/auth';
import { ensureProduct, addStock } from './helpers/data';

const API = 'http://localhost:8000/api/v1';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/inventory');
  await expect(page.getByRole('heading', { name: 'Inventory' })).toBeVisible();
});

// ---------------------------------------------------------------------------
// Inventory page basics
// ---------------------------------------------------------------------------

test('shows Inventory heading and stock levels table', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Inventory' })).toBeVisible();
  await expect(page.getByText('Current Stock Levels')).toBeVisible();
  await expect(page.getByText('Recent Movements')).toBeVisible();
});

// ---------------------------------------------------------------------------
// Stock adjustment dialog
// ---------------------------------------------------------------------------

test('clicking Adjust opens the Adjust Stock dialog', async ({ page }) => {
  // Only run if there are inventory rows
  const adjustButtons = page.locator('button', { hasText: 'Adjust' });
  const count = await adjustButtons.count();
  if (count === 0) {
    test.skip();
    return;
  }

  await adjustButtons.first().click();

  const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Adjust Stock' });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('#inv-adjust-type')).toBeVisible();
  await expect(dialog.locator('#inv-adjust-qty')).toBeVisible();
  await expect(dialog.locator('#inv-adjust-reason')).toBeVisible();
});

test('Adjust dialog has correct movement type options', async ({ page }) => {
  const adjustButtons = page.locator('button', { hasText: 'Adjust' });
  const count = await adjustButtons.count();
  if (count === 0) {
    test.skip();
    return;
  }

  await adjustButtons.first().click();
  const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Adjust Stock' });
  await expect(dialog).toBeVisible();

  const select = dialog.locator('#inv-adjust-type');
  const options = await select.locator('option').allTextContents();
  expect(options).toContain('Purchase / Restock');
  expect(options).toContain('Manual Add');
  expect(options).toContain('Manual Remove');
  expect(options).toContain('Damage / Loss');
});

test('can submit a stock adjustment and see success toast', async ({ page }) => {
  // Seed a product with stock via API so the test never skips
  const product = await ensureProduct(`E2E Adj Product ${Date.now()}`);
  await addStock(product.id, 20);

  await page.reload();
  await expect(page.getByRole('heading', { name: 'Inventory' })).toBeVisible();

  // Locate the Adjust button for our seeded product
  const row = page.getByRole('row').filter({ hasText: product.name }).first();
  await expect(row).toBeVisible({ timeout: 10_000 });
  await row.getByRole('button', { name: 'Adjust' }).click();

  const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Adjust Stock' });
  await expect(dialog).toBeVisible();

  // Select type, enter quantity and reason (required field)
  await dialog.locator('#inv-adjust-type').selectOption('manual_add');
  await dialog.locator('#inv-adjust-qty').fill('5');
  await dialog.locator('#inv-adjust-reason').fill('E2E test adjustment');

  await dialog.getByRole('button', { name: 'Save Adjustment' }).click();

  // Success toast must appear — NOT the 'Failed to adjust stock' error
  await expect(page.getByText('Stock updated successfully')).toBeVisible({ timeout: 10_000 });
});

test('reason field is required — empty reason prevents submit', async ({ page }) => {
  const adjustButtons = page.locator('button', { hasText: 'Adjust' });
  const count = await adjustButtons.count();
  if (count === 0) {
    test.skip();
    return;
  }

  await adjustButtons.first().click();
  const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Adjust Stock' });
  await expect(dialog).toBeVisible();

  await dialog.locator('#inv-adjust-qty').fill('3');
  // Leave reason empty — button should be disabled
  const saveBtn = dialog.getByRole('button', { name: 'Save Adjustment' });
  await expect(saveBtn).toBeDisabled();
});
