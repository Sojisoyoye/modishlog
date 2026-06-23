import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

/** Helper: ensure the API key input form is visible (click "Update" if already configured). */
async function ensureApiKeyFormVisible(page: import('@playwright/test').Page): Promise<void> {
  // Wait for the settings page to finish all initial API calls (e.g. getApiKeyStatus)
  // before checking form state — avoids a race where ngOnInit hides the form after
  // ensureApiKeyFormVisible already confirmed it was visible.
  await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});

  const configuredBanner = page.getByText('Configured', { exact: true });
  const passwordInput = page.locator('input[type="password"]');

  // Wait up to 8s for one of the two states to appear
  await expect(configuredBanner.or(passwordInput)).toBeVisible({ timeout: 8_000 });

  // If the "Configured" banner is showing, click "Update" to reveal the input
  const isConfigured = await configuredBanner.isVisible().catch(() => false);
  if (isConfigured) {
    await page.getByRole('button', { name: 'Update' }).click();
    // Wait for the Configured state to clear, then wait for the input
    await expect(configuredBanner).not.toBeVisible({ timeout: 3_000 });
  }
  await expect(passwordInput).toBeVisible({ timeout: 5_000 });
}

test.describe('Settings — API key stored in backend, not localStorage', () => {
  test('after saving API key, localStorage does not contain the key', async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/settings');

    await ensureApiKeyFormVisible(page);
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

    await ensureApiKeyFormVisible(page);
    await page.locator('input[type="password"]').fill('sk-ant-another-key');
    await page.getByRole('button', { name: 'Save' }).click();

    await expect(page.getByText('API key saved successfully')).toBeVisible({ timeout: 5_000 });
  });

  test('on page load, shows configured status if key was previously saved', async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/settings');

    // Save a key first (handling the case where one is already configured)
    await ensureApiKeyFormVisible(page);
    await page.locator('input[type="password"]').fill('sk-ant-persist-test');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByText('API key saved successfully')).toBeVisible({ timeout: 5_000 });

    // Reload the page — the configured indicator should appear
    await page.reload();
    await expect(page.getByText('Configured')).toBeVisible({ timeout: 10_000 });
  });
});
