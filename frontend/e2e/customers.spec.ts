import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/customers');
  await expect(page.getByRole('heading', { name: 'Customers' })).toBeVisible({ timeout: 15000 });
});

test('customers list loads', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Customers' })).toBeVisible();
  await expect(page.getByRole('table')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add Customer' })).toBeVisible();
});

test('create customer', async ({ page }) => {
  const name = `E2E Customer ${Date.now()}`;
  await page.getByRole('button', { name: 'Add Customer' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();

  await page.getByPlaceholder('Customer name').fill(name);
  await page.getByPlaceholder('Email address').fill('test@example.com');
  await page.getByRole('button', { name: 'Save Customer' }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden' });

  await page.getByPlaceholder('Search customers...').fill(name);
  await page.waitForTimeout(400);
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible({ timeout: 5000 });
});

test('edit customer', async ({ page }) => {
  const name = `Edit Customer ${Date.now()}`;
  await page.getByRole('button', { name: 'Add Customer' }).click();
  await page.getByPlaceholder('Customer name').fill(name);
  await page.getByRole('button', { name: 'Save Customer' }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden' });

  await page.getByPlaceholder('Search customers...').fill(name);
  await page.waitForTimeout(400);
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible({ timeout: 5000 });

  await page.getByTestId(`edit-customer-${name}`).click();
  await page.getByPlaceholder('City').fill('Lagos');
  await page.getByRole('button', { name: 'Save Customer' }).click();
  await expect(page.getByText('Customer updated', { exact: true })).toBeVisible({ timeout: 5000 });
});

test('filter by active status', async ({ page }) => {
  // Create a customer (starts active), then deactivate it
  const name = `Filter Customer ${Date.now()}`;
  await page.getByRole('button', { name: 'Add Customer' }).click();
  await page.getByPlaceholder('Customer name').fill(name);
  await page.getByRole('button', { name: 'Save Customer' }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden' });

  // Search so it's visible
  await page.getByPlaceholder('Search customers...').fill(name);
  await page.waitForTimeout(400);
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible({ timeout: 5000 });

  // Toggle it inactive via the power button (title = "Deactivate")
  await page.getByRole('button', { name: 'Deactivate' }).click();
  await page.waitForTimeout(400);

  // Active filter: customer should NOT appear
  await page.getByRole('button', { name: 'Active' }).click();
  await page.waitForTimeout(400);
  await expect(page.getByRole('cell', { name, exact: true })).not.toBeVisible();

  // Inactive filter: customer MUST appear
  await page.getByRole('button', { name: 'Inactive' }).click();
  await page.waitForTimeout(400);
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible({ timeout: 5000 });
});
