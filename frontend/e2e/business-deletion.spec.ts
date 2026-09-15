/**
 * Self-service business account deletion (task #252).
 *
 * Uses a dedicated, freshly-onboarded business per test run (NOT the
 * shared E2E_EMAIL/E2E_PASSWORD business used across the rest of the
 * suite) -- scheduling deletion blocks login for every user in the
 * business, which would break every other spec relying on the shared
 * account if run against it.
 */

import { test, expect, APIRequestContext } from '@playwright/test';

const API = 'http://localhost:8000/api/v1';
const PASSWORD = 'DeleteTest!1234';

async function onboard(request: APIRequestContext, email: string, businessName: string) {
  const resp = await request.post(`${API}/auth/onboard`, {
    data: {
      full_name: 'Deletion Test Owner',
      email,
      password: PASSWORD,
      business_name: businessName,
      ndpr_consent: true,
    },
  });
  expect(resp.ok(), `onboard failed: ${resp.status()} ${await resp.text()}`).toBe(true);
}

test.describe('Business account deletion', () => {
  test('owner can schedule and cancel deletion from the Danger Zone', async ({ page }) => {
    const email = `deletion-test-${Date.now()}@modishlogtest.com`;
    const businessName = `Deletion Test Biz ${Date.now()}`;
    await onboard(page.request, email, businessName);

    // Log in via the UI (also verifies the login form itself still works
    // normally for an account with nothing scheduled).
    await page.goto('/login');
    await page.getByPlaceholder('you@example.com').fill(email);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole('button', { name: 'Sign In' }).click();
    await page.waitForURL('**/dashboard', { timeout: 20_000 });

    await page.goto('/settings');
    await page.waitForLoadState('networkidle');

    const dangerZone = page.getByTestId('danger-zone');
    await expect(dangerZone).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('delete-business-btn')).toBeVisible();
    await expect(page.getByTestId('deletion-pending-banner')).toHaveCount(0);

    // Open the confirm modal -- button must stay disabled until the exact
    // business name is typed.
    await page.getByTestId('delete-business-btn').click();
    // PrimeNG's <p-dialog> host element itself doesn't reflect visibility
    // the way Playwright's toBeVisible() checks (the actual rendered
    // dialog content is what becomes visible) -- assert on content inside
    // it instead of the data-testid on the host tag.
    const confirmInput = page.getByTestId('delete-confirm-input');
    await expect(confirmInput).toBeVisible();
    const confirmBtn = page.getByTestId('confirm-delete-business-btn');
    await expect(confirmBtn).toBeDisabled();

    await confirmInput.fill('the wrong name entirely');
    await expect(confirmBtn).toBeDisabled();

    await confirmInput.fill(businessName);
    await expect(confirmBtn).toBeEnabled();
    await confirmBtn.click();

    // Deletion scheduled: pending banner replaces the delete button.
    await expect(page.getByTestId('deletion-pending-banner')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('delete-business-btn')).toHaveCount(0);
    await expect(page.locator('body')).toContainText(/permanently deleted on/i);

    // Cancel within the grace period restores normal state.
    await page.getByTestId('cancel-deletion-btn').click();
    await expect(page.getByTestId('deletion-pending-banner')).toHaveCount(0, { timeout: 10_000 });
    await expect(page.getByTestId('delete-business-btn')).toBeVisible();

    // Login must still work normally after cancelling.
    await page.context().clearCookies();
    await page.goto('/login');
    await page.getByPlaceholder('you@example.com').fill(email);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole('button', { name: 'Sign In' }).click();
    await page.waitForURL('**/dashboard', { timeout: 20_000 });
  });

  test('login is blocked with a clear message while deletion is pending', async ({ page }) => {
    const email = `deletion-block-test-${Date.now()}@modishlogtest.com`;
    const businessName = `Deletion Block Biz ${Date.now()}`;
    await onboard(page.request, email, businessName);

    await page.goto('/login');
    await page.getByPlaceholder('you@example.com').fill(email);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole('button', { name: 'Sign In' }).click();
    await page.waitForURL('**/dashboard', { timeout: 20_000 });

    await page.goto('/settings');
    await page.waitForLoadState('networkidle');
    await page.getByTestId('delete-business-btn').click();
    await page.getByTestId('delete-confirm-input').fill(businessName);
    await page.getByTestId('confirm-delete-business-btn').click();
    await expect(page.getByTestId('deletion-pending-banner')).toBeVisible({ timeout: 10_000 });

    // Log out (refresh token revoked server-side already) and try to log
    // back in -- must be blocked with the deletion-specific message, not
    // the generic "please verify your email" affordance.
    await page.context().clearCookies();
    await page.goto('/login');
    await page.getByPlaceholder('you@example.com').fill(email);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole('button', { name: 'Sign In' }).click();

    await expect(page.locator('body')).toContainText(/scheduled for deletion/i, { timeout: 10_000 });
    await expect(page.locator('body')).not.toContainText(/resend verification/i);
    await expect(page).toHaveURL(/\/login/);
  });
});
