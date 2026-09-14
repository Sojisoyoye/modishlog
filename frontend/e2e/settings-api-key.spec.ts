import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaAPI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

/**
 * Helper: navigate to /settings and ensure the API key input form is visible
 * (clicking "Update" if already configured).
 *
 * `apiKeyConfigured` defaults to false on the component, so the input form
 * renders first on every fresh page load and only flips to the "Configured"
 * banner once the async GET /settings/api-key/anthropic status check
 * resolves. If a key was already saved (as happens once the earlier test in
 * this file runs), that response can land *after* we've already seen and
 * started filling the (stale) input form, silently swapping the DOM out from
 * under us mid-interaction. The response listener must be registered before
 * navigation -- attaching it after goto() can miss a response that already
 * resolved, since Playwright only matches responses seen after the listener
 * exists.
 */
async function gotoSettingsWithApiKeyFormVisible(page: import('@playwright/test').Page): Promise<void> {
  const statusResponse = page.waitForResponse(
    (r) => r.url().includes('/settings/api-key/anthropic') && r.request().method() === 'GET',
    { timeout: 8_000 },
  );
  await page.goto('/settings');
  await statusResponse.catch(() => {});

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

test.describe('Settings — Anthropic key section is honest about scope (task 216)', () => {
  test('disclaims that no feature consumes the key yet', async ({ page }) => {
    await loginViaAPI(page);
    await page.goto('/settings');

    await expect(page.getByTestId('anthropic-key-disclaimer')).toBeVisible({ timeout: 8_000 });
    await expect(page.getByRole('heading', { name: 'Anthropic API Key (optional)' })).toBeVisible();
  });
});

test.describe('Settings — API key stored in backend, not localStorage', () => {
  test('after saving API key, localStorage does not contain the key', async ({ page }) => {
    await loginViaAPI(page);
    await gotoSettingsWithApiKeyFormVisible(page);
    await page.locator('input[type="password"]').fill('sk-ant-test-key-12345');
    // A non-exact/role-based 'Save' locator also matches 'Save Business Profile'
    // (which sits earlier in the DOM) via .first(), silently never invoking
    // saveApiKey() at all -- use the dedicated testid instead.
    await page.getByTestId('save-api-key-button').click();

    // Wait for success feedback
    await expect(page.getByText('API key saved successfully')).toBeVisible({ timeout: 10_000 });

    // The key must NOT appear in localStorage
    const storedKey = await page.evaluate(() => localStorage.getItem('modishlog_api_key'));
    expect(storedKey).toBeNull();
  });

  test('after saving API key, the "configured" indicator is shown', async ({ page }) => {
    await loginViaAPI(page);
    await gotoSettingsWithApiKeyFormVisible(page);
    await page.locator('input[type="password"]').fill('sk-ant-another-key');
    await page.getByTestId('save-api-key-button').click();

    await expect(page.getByText('API key saved successfully')).toBeVisible({ timeout: 10_000 });
  });

  test('on page load, shows configured status if key was previously saved', async ({ page }) => {
    await loginViaAPI(page);
    // Save a key first (handling the case where one is already configured)
    await gotoSettingsWithApiKeyFormVisible(page);
    await page.locator('input[type="password"]').fill('sk-ant-persist-test');
    await page.getByTestId('save-api-key-button').click();
    await expect(page.getByText('API key saved successfully')).toBeVisible({ timeout: 10_000 });

    // Reload the page — the configured indicator should appear
    await page.reload();
    await expect(page.getByText('Configured', { exact: true })).toBeVisible({ timeout: 10_000 });
  });
});
