import { test, expect, request as pwRequest } from '@playwright/test';

const API = 'http://localhost:8000/api/v1';
// 14 chars, meets backend policy: 12+, upper, lower, digit, special
const PASSWORD = 'E2eBanner!Pass14';

// ---------------------------------------------------------------------------
// Subscription status banner (task #240) -- a freshly-onboarded business is
// always `trialing` by default, so this is testable without any way to force
// other subscription states (past_due/read_only) through the public API,
// which intentionally doesn't exist.
// ---------------------------------------------------------------------------

test.describe('Subscription trial banner', () => {
  test('shows a trial countdown right after onboarding a new business', async ({ page }) => {
    const email = `banner-${Date.now()}@modishlogtest.com`;
    const ctx = await pwRequest.newContext();
    try {
      const resp = await ctx.post(`${API}/auth/onboard`, {
        data: {
          full_name: 'Banner Tester',
          email,
          password: PASSWORD,
          business_name: `E2E Banner Test ${Date.now()}`,
          ndpr_consent: true,
        },
      });
      expect(resp.ok()).toBeTruthy();
    } finally {
      await ctx.dispose();
    }

    await page.goto('/login');
    await page.getByPlaceholder('you@example.com').fill(email);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole('button', { name: 'Sign In' }).click();
    await page.waitForURL('**/dashboard', { timeout: 20_000 });

    const banner = page.getByTestId('subscription-banner');
    await expect(banner).toBeVisible();
    await expect(banner).toHaveText(/\d+ days? left in your free trial\./);
  });
});
