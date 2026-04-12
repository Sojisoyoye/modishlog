import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI, E2E_EMAIL, E2E_PASSWORD } from './helpers/auth';

// ---------------------------------------------------------------------------
// Auth / Login E2E Tests
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Login page rendering', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('displays the ModishLog title', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'ModishLog' })).toBeVisible();
  });

  test('displays email and password fields', async ({ page }) => {
    await expect(page.getByPlaceholder('you@example.com')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });

  test('displays Sign In button', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });

  test('displays the "M" logo mark', async ({ page }) => {
    // The logo is a div with rounded-xl bg-primary containing just "M"
    const logo = page.locator('.rounded-xl.bg-primary').filter({ hasText: 'M' }).first();
    await expect(logo).toBeVisible();
  });
});

test.describe('Login functionality', () => {
  test('shows error with wrong credentials', async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder('you@example.com').fill('wrong@example.com');
    await page.locator('input[type="password"]').fill('wrongpassword123');
    await page.getByRole('button', { name: 'Sign In' }).click();

    // Should show an error message (401 -> "Invalid email or password.")
    await expect(page.getByText('Invalid email or password')).toBeVisible({ timeout: 10_000 });
    // Should stay on login page
    await expect(page).toHaveURL(/\/login/);
  });

  test('logs in successfully and redirects to dashboard', async ({ page }) => {
    await loginViaUI(page);
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });

  test('unauthenticated access redirects to login', async ({ page }) => {
    // Clear any stored token
    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => localStorage.clear());

    // Try to access protected route
    await page.goto('/dashboard');
    await page.waitForURL('**/login', { timeout: 10_000 });
    await expect(page).toHaveURL(/\/login/);
  });

  test('logout returns to login page', async ({ page }) => {
    await loginViaUI(page);
    await expect(page).toHaveURL(/\/dashboard/);

    // Click the Logout button in the topbar
    await page.getByRole('button', { name: 'Logout' }).click();
    await page.waitForURL('**/login', { timeout: 10_000 });
    await expect(page).toHaveURL(/\/login/);
  });
});
