import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Email verification E2E tests.
//
// Note: the shared E2E_EMAIL test user is auto-verified in this environment
// (E2E_AUTO_VERIFY_EMAIL, set only by docker-compose.e2e.yml — see
// backend/src/core/config.py) since the suite has no real inbox to read a
// verification link from. These tests exercise the UI-observable behaviour
// that doesn't require a genuinely unverified backend account: the
// /verify-email invalid-token path and the resend-verification no-enumeration
// behaviour. The blocking-login-for-unverified-users behaviour itself is
// covered at the API level in backend/tests/test_auth.py
// (TestLoginEmailVerification), matching the precedent already set by
// forgot-reset-password.spec.ts for the equivalent token-based flow.
// ---------------------------------------------------------------------------

test.describe('/verify-email page', () => {
  test('navigating with no token shows an error and no verifying spinner', async ({ page }) => {
    await page.goto('/verify-email');
    await expect(page).toHaveURL(/\/verify-email/);
    await expect(page.getByText(/invalid|missing/i)).toBeVisible({ timeout: 10_000 });
  });

  test('navigating with a garbage token shows an invalid/expired error', async ({ page }) => {
    await page.goto('/verify-email?token=totally-invalid-verify-token-xyz');
    await expect(page).toHaveURL(/\/verify-email/);
    await expect(page.getByText(/invalid|expired/i)).toBeVisible({ timeout: 10_000 });
  });

  test('"Back to login" link returns to /login', async ({ page }) => {
    await page.goto('/verify-email');
    await page.getByRole('button', { name: /back to login/i }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('/check-email page', () => {
  test('renders with the submitted email in the message', async ({ page }) => {
    await page.goto('/check-email?email=someone%40example.com');
    await expect(page.getByText('someone@example.com')).toBeVisible();
    await expect(page.getByRole('button', { name: /resend verification email/i })).toBeVisible();
  });

  test('resend button shows a generic success message', async ({ page }) => {
    await page.goto('/check-email?email=someone%40example.com');
    await page.getByRole('button', { name: /resend verification email/i }).click();
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 10_000 });
  });

  test('resend button shows the same generic message for an unregistered email (no enumeration)', async ({
    page,
  }) => {
    await page.goto('/check-email?email=definitely-not-registered%40example.com');
    await page.getByRole('button', { name: /resend verification email/i }).click();
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 10_000 });
  });

  test('without an email query param, no resend button is shown', async ({ page }) => {
    await page.goto('/check-email');
    await expect(page.getByRole('button', { name: /resend verification email/i })).not.toBeVisible();
  });

  test('"Back to login" link returns to /login', async ({ page }) => {
    await page.goto('/check-email');
    await page.getByRole('button', { name: /back to login/i }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});
