import { test, expect, request as pwRequest } from '@playwright/test';

const API = 'http://localhost:8000/api/v1';
// 14 chars, meets backend policy: 12+, upper, lower, digit, special
const PASSWORD = 'E2eBilling!Pass14';

// ---------------------------------------------------------------------------
// Settings > Subscription & Billing (task #241) -- a freshly-onboarded
// business is always `trialing` (OWNER role) by default, so this is
// testable without any way to force other subscription states through the
// public API. No Paystack account/sandbox exists yet (disclosed limitation
// shared with tasks #238/#239), so CI's /billing/checkout call is expected
// to fail with a real 503/502 -- this test asserts that failure surfaces as
// a visible error toast, not that checkout actually succeeds.
// ---------------------------------------------------------------------------

test.describe('Settings — Subscription & Billing', () => {
  test('shows trial status and subscribe buttons, and surfaces a checkout error gracefully', async ({
    page,
  }) => {
    const email = `billing-${Date.now()}@modishlogtest.com`;
    const ctx = await pwRequest.newContext();
    try {
      const resp = await ctx.post(`${API}/auth/onboard`, {
        data: {
          full_name: 'Billing Tester',
          email,
          password: PASSWORD,
          business_name: `E2E Billing Test ${Date.now()}`,
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

    await page.goto('/settings');

    await expect(page.getByTestId('billing-status')).toContainText(/trial/i);
    await expect(page.getByTestId('billing-subscribe-basic')).toBeVisible();
    await expect(page.getByTestId('billing-subscribe-pro')).toBeVisible();

    await page.getByTestId('billing-subscribe-basic').click();

    // No Paystack plan codes are configured in CI -- the backend genuinely
    // returns 503/502 here, and that must surface as a toast, not a hang
    // or a silent failure.
    await expect(page.locator('.p-toast')).toBeVisible({ timeout: 10_000 });
  });
});
