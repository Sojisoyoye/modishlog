import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/settings');
});

test.describe('Settings — Business Profile', () => {
  test('business profile section is visible on settings page', async ({ page }) => {
    await expect(page.getByText('Business Profile', { exact: true })).toBeVisible();
  });

  test('can save business profile and see saved confirmation', async ({ page }) => {
    await page.getByPlaceholder('e.g. Ade Traders Ltd').fill('Test Business Ltd');
    await page.getByPlaceholder('e.g. +234 801 234 5678').fill('+234 800 000 0001');
    await page.getByRole('button', { name: 'Save Business Profile' }).click();
    await expect(page.getByText('Saved')).toBeVisible({ timeout: 10_000 });
  });

  test('business profile persists after page reload', async ({ page }) => {
    await page.getByPlaceholder('e.g. Ade Traders Ltd').fill('Persist Test Co');
    await page.getByRole('button', { name: 'Save Business Profile' }).click();
    await expect(page.getByText('Saved')).toBeVisible({ timeout: 10_000 });

    await page.reload();
    await expect(page.getByPlaceholder('e.g. Ade Traders Ltd')).toHaveValue('Persist Test Co', {
      timeout: 10_000,
    });
  });
});

test.describe('Settings — App Preferences', () => {
  test('preferences section is visible', async ({ page }) => {
    await expect(page.getByText('General Preferences', { exact: true })).toBeVisible();
  });

  test('can save preferences and see saved confirmation', async ({ page }) => {
    await page.getByRole('button', { name: 'Save Preferences' }).click();
    await expect(page.locator('text=Saved').last()).toBeVisible({ timeout: 10_000 });
  });
});
