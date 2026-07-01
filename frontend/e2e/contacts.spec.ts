import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
});

test('contacts page defaults to Suppliers tab', async ({ page }) => {
  await page.goto('/contacts');
  await expect(page.getByRole('heading', { name: 'Contacts' })).toBeVisible({ timeout: 15000 });
  // Suppliers tab is active by default
  await expect(page.getByRole('tab', { name: 'Suppliers' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('heading', { name: 'Suppliers' })).toBeVisible();
});

test('contacts page switches to Customers tab', async ({ page }) => {
  await page.goto('/contacts');
  await expect(page.getByRole('heading', { name: 'Contacts' })).toBeVisible({ timeout: 15000 });
  await page.getByRole('tab', { name: 'Customers' }).click();
  await expect(page.getByRole('heading', { name: 'Customers' })).toBeVisible();
});

test('contacts page shows Customers tab when ?tab=customers query param is set', async ({ page }) => {
  await page.goto('/contacts?tab=customers');
  await expect(page.getByRole('heading', { name: 'Contacts' })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole('heading', { name: 'Customers' })).toBeVisible();
});

test('sidebar shows Contacts link instead of separate Suppliers and Customers links', async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page.getByRole('link', { name: 'Contacts' })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole('link', { name: 'Suppliers' })).not.toBeVisible();
  await expect(page.getByRole('link', { name: 'Customers' })).not.toBeVisible();
});

test('clicking Contacts nav link opens contacts page', async ({ page }) => {
  await page.goto('/dashboard');
  await page.getByRole('link', { name: 'Contacts' }).click();
  await expect(page.getByRole('heading', { name: 'Contacts' })).toBeVisible({ timeout: 15000 });
});
