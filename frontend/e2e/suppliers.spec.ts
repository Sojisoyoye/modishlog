import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/suppliers');
  await expect(page.getByRole('heading', { name: 'Suppliers' })).toBeVisible();
});

test('shows Suppliers heading and Add Supplier button', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Suppliers' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add Supplier' })).toBeVisible();
});

test('opens add supplier dialog and shows required fields', async ({ page }) => {
  await page.getByRole('button', { name: 'Add Supplier' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByPlaceholder('Supplier name')).toBeVisible();
  await expect(page.getByPlaceholder('Contact person')).toBeVisible();
  await expect(page.getByPlaceholder('Email address')).toBeVisible();
  await expect(page.getByPlaceholder('Mobile number')).toBeVisible();
});

test('creates a supplier and shows it in the list', async ({ page }) => {
  const name = `Test Supplier ${Date.now()}`;
  await page.getByRole('button', { name: 'Add Supplier' }).click();
  await page.getByPlaceholder('Supplier name').fill(name);
  await page.getByPlaceholder('Contact person').fill('Jane Doe');
  await page.getByPlaceholder('Email address').fill('jane@test.com');
  await page.getByRole('button', { name: 'Save Supplier' }).click();
  await expect(page.getByText(name)).toBeVisible({ timeout: 5000 });
});

test('opens supplier detail and shows tabs', async ({ page }) => {
  const name = `Detail Supplier ${Date.now()}`;
  await page.getByRole('button', { name: 'Add Supplier' }).click();
  await page.getByPlaceholder('Supplier name').fill(name);
  await page.getByRole('button', { name: 'Save Supplier' }).click();
  await expect(page.getByText(name)).toBeVisible({ timeout: 5000 });

  await page.getByText(name).click();
  await expect(page.getByRole('tab', { name: 'Purchases' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Stock Report' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Activities' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Ledger' })).toBeVisible();
});

test('can switch between supplier detail tabs', async ({ page }) => {
  const name = `Tab Supplier ${Date.now()}`;
  await page.getByRole('button', { name: 'Add Supplier' }).click();
  await page.getByPlaceholder('Supplier name').fill(name);
  await page.getByRole('button', { name: 'Save Supplier' }).click();
  await expect(page.getByText(name)).toBeVisible({ timeout: 5000 });

  await page.getByText(name).click();
  await page.getByRole('tab', { name: 'Ledger' }).click();
  await expect(page.getByRole('table')).toBeVisible();

  await page.getByRole('tab', { name: 'Activities' }).click();
  await expect(page.getByText('No activity yet.')).toBeVisible();
});

test('edits a supplier', async ({ page }) => {
  const name = `Edit Me ${Date.now()}`;
  await page.getByRole('button', { name: 'Add Supplier' }).click();
  await page.getByPlaceholder('Supplier name').fill(name);
  await page.getByRole('button', { name: 'Save Supplier' }).click();
  await expect(page.getByText(name)).toBeVisible({ timeout: 5000 });

  await page.getByTestId(`edit-supplier-${name}`).click();
  await page.getByPlaceholder('Contact person').fill('Updated Contact');
  await page.getByRole('button', { name: 'Save Supplier' }).click();
  await expect(page.getByText('Supplier updated')).toBeVisible({ timeout: 5000 });
});
