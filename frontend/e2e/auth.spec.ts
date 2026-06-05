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

test.describe('Password visibility toggle', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('password input starts as type password', async ({ page }) => {
    const passwordInput = page.locator('#login-password');
    await expect(passwordInput).toHaveAttribute('type', 'password');
  });

  test('clicking eye toggle changes password input to type text', async ({ page }) => {
    const passwordInput = page.locator('#login-password');
    const toggleButton = page.locator('[data-testid="toggle-password"]');

    await expect(passwordInput).toHaveAttribute('type', 'password');
    await toggleButton.click();
    await expect(passwordInput).toHaveAttribute('type', 'text');
  });

  test('clicking eye toggle again reverts input back to type password', async ({ page }) => {
    const passwordInput = page.locator('#login-password');
    const toggleButton = page.locator('[data-testid="toggle-password"]');

    await toggleButton.click();
    await expect(passwordInput).toHaveAttribute('type', 'text');
    await toggleButton.click();
    await expect(passwordInput).toHaveAttribute('type', 'password');
  });

  test('toggle button shows pi-eye icon initially', async ({ page }) => {
    const toggleButton = page.locator('[data-testid="toggle-password"]');
    const icon = toggleButton.locator('i');
    await expect(icon).toHaveClass(/pi-eye/);
  });

  test('toggle button shows pi-eye-slash icon after clicking once', async ({ page }) => {
    const toggleButton = page.locator('[data-testid="toggle-password"]');
    await toggleButton.click();
    const icon = toggleButton.locator('i');
    await expect(icon).toHaveClass(/pi-eye-slash/);
  });

  test('form still submits correctly after toggling password visibility', async ({ page }) => {
    const toggleButton = page.locator('[data-testid="toggle-password"]');

    // Toggle visibility then fill in credentials and submit
    await toggleButton.click();
    await page.getByPlaceholder('you@example.com').fill('wrong@example.com');
    await page.locator('#login-password').fill('wrongpassword123');
    await page.getByRole('button', { name: 'Sign In' }).click();

    // Should still attempt login and show error for wrong credentials
    await expect(page.getByText('Invalid email or password')).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/login/);
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
