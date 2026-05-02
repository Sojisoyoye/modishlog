import { test, expect, request as pwRequest } from '@playwright/test';
import { ensureTestUser, loginViaUI, E2E_EMAIL, E2E_PASSWORD } from './helpers/auth';

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
  // Ensure there is at least one product with inventory via API first
  const ctx = await pwRequest.newContext();
  const loginResp = await ctx.post(`${API}/auth/login`, {
    data: { email: E2E_EMAIL, password: E2E_PASSWORD },
  });
  const { access_token } = await loginResp.json();

  // Check inventory exists
  const invResp = await ctx.get(`${API}/inventory`, {
    headers: { Authorization: `Bearer ${access_token}` },
  });
  const inventory = await invResp.json();
  await ctx.dispose();

  if (!Array.isArray(inventory) || inventory.length === 0) {
    test.skip();
    return;
  }

  await page.reload();
  await expect(page.getByRole('heading', { name: 'Inventory' })).toBeVisible();

  const adjustButtons = page.locator('button', { hasText: 'Adjust' });
  await expect(adjustButtons.first()).toBeVisible({ timeout: 10_000 });
  await adjustButtons.first().click();

  const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Adjust Stock' });
  await expect(dialog).toBeVisible();

  // Select type, enter quantity and reason (required field)
  await dialog.locator('#inv-adjust-type').selectOption('manual_add');
  await dialog.locator('#inv-adjust-qty').fill('5');
  await dialog.locator('#inv-adjust-reason').fill('E2E test adjustment');

  await dialog.getByRole('button', { name: 'Save Adjustment' }).click();

  // Success toast should appear
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
