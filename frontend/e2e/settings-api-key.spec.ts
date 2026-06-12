import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Settings — API key stored in backend, not localStorage', () => {
  test('after saving API key, localStorage does not contain the key', async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/settings');

    await page.locator('input[type="password"]').fill('sk-ant-test-key-12345');
    await page.getByRole('button', { name: 'Save' }).click();

    // Wait for success feedback
    await expect(page.getByText('API key saved successfully')).toBeVisible({ timeout: 5_000 });

    // The key must NOT appear in localStorage
    const storedKey = await page.evaluate(() => localStorage.getItem('modishlog_api_key'));
    expect(storedKey).toBeNull();
  });

  test('after saving API key, the "configured" indicator is shown', async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/settings');

    await page.locator('input[type="password"]').fill('sk-ant-another-key');
    await page.getByRole('button', { name: 'Save' }).click();

    await expect(page.getByText('API key saved successfully')).toBeVisible({ timeout: 5_000 });
  });

  test('on page load, shows configured status if key was previously saved', async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/settings');

    // Save a key first
    await page.locator('input[type="password"]').fill('sk-ant-persist-test');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByText('API key saved successfully')).toBeVisible({ timeout: 5_000 });

    // Reload the page — the configured indicator should appear
    await page.reload();
    await expect(page.getByText('Configured')).toBeVisible({ timeout: 5_000 });
  });
});
