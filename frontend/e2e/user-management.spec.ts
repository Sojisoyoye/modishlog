import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaAPI, E2E_EMAIL } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaAPI(page);
});

test.describe('User Management — Users page', () => {
  test('Users link is visible in sidebar under Settings', async ({ page }) => {
    await page.goto('/settings/users');
    await expect(page).toHaveURL('/settings/users');
  });

  test('Users page shows page heading', async ({ page }) => {
    await page.goto('/settings/users');
    await expect(page.getByRole('heading', { name: /users/i })).toBeVisible({ timeout: 10_000 });
  });

  test('Users page shows current admin user in list', async ({ page }) => {
    await page.goto('/settings/users');
    await expect(page.getByText(E2E_EMAIL)).toBeVisible({ timeout: 10_000 });
  });

  test('Invite User button is visible on Users page', async ({ page }) => {
    await page.goto('/settings/users');
    await expect(page.getByRole('button', { name: /invite user/i })).toBeVisible({ timeout: 10_000 });
  });

  test('Invite User dialog opens on button click', async ({ page }) => {
    await page.goto('/settings/users');
    await page.getByRole('button', { name: /invite user/i }).click();
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/full name/i)).toBeVisible();
  });

  test('Invite User dialog closes on cancel', async ({ page }) => {
    await page.goto('/settings/users');
    await page.getByRole('button', { name: /invite user/i }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.getByRole('button', { name: /cancel/i }).click();
    await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 3_000 });
  });

  test('Users list shows role badge for admin', async ({ page }) => {
    await page.goto('/settings/users');
    await expect(page.getByText(/admin/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test('Users page has search input', async ({ page }) => {
    await page.goto('/settings/users');
    await expect(page.getByPlaceholder(/search/i)).toBeVisible({ timeout: 10_000 });
  });

  test('reset password confirms, calls the API, and shows a success toast -- never displays the raw token (task #224)', async ({ page }) => {
    await page.goto('/settings/users');
    await expect(page.getByText(E2E_EMAIL)).toBeVisible({ timeout: 10_000 });

    // doResetPassword() uses a native confirm() before submitting.
    page.once('dialog', (dialog) => dialog.accept());

    const [resetResponse] = await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('/reset-password') && resp.status() === 200,
      ),
      page.getByRole('button', { name: /reset password/i }).first().click(),
    ]);

    const body = await resetResponse.json();
    expect(body).toEqual({ message: expect.any(String) });
    expect(body).not.toHaveProperty('token');

    await expect(page.getByText(/reset email sent/i)).toBeVisible({ timeout: 5_000 });

    // The raw token must never reach the page -- no dialog, no input field
    // holding it (this replaces the old "copy the token" UI entirely).
    await expect(page.getByRole('dialog')).not.toBeVisible();
  });
});
