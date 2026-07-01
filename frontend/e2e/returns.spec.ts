import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/returns');
  await expect(page.getByRole('heading', { name: 'Returns' })).toBeVisible({ timeout: 15000 });
});

test('returns page loads with tabs', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Returns' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sell Returns' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Purchase Returns' })).toBeVisible();
});

test('sell returns tab shows list', async ({ page }) => {
  await page.getByRole('button', { name: 'Sell Returns' }).click();
  await expect(page.getByRole('table')).toBeVisible({ timeout: 10000 });
});

test('purchase returns tab shows list', async ({ page }) => {
  await page.getByRole('button', { name: 'Purchase Returns' }).click();
  await expect(page.getByRole('table')).toBeVisible({ timeout: 10000 });
});
