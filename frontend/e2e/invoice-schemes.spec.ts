import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/settings/invoice-schemes');
});

test('shows heading and Add Scheme button', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Invoice Schemes' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Add Scheme/i })).toBeVisible();
});

test('opens add scheme dialog with type radio buttons', async ({ page }) => {
  await page.getByRole('button', { name: /Add Scheme/i }).click();
  await expect(page.getByText(/blank/i).first()).toBeVisible();
  await expect(page.getByText(/year/i).first()).toBeVisible();
});
