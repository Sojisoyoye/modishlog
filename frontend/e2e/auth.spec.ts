import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken, E2E_EMAIL, E2E_PASSWORD } from './helpers/auth';

const API = 'http://localhost:8000/api/v1';
const LOCKOUT_EMAIL = 'e2e-lockout@modishlogtest.com';
const LOCKOUT_PASSWORD = 'E2eLock0ut!Pass';
const WRONG_PASSWORD = 'WrongPassword!99';
const LOCKOUT_THRESHOLD = 3;

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

test.describe('Account lockout', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeAll(async () => {
    const token = await getAPIToken();
    const ctx = await request.newContext();
    try {
      await ctx.post(`${API}/auth/register`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { email: LOCKOUT_EMAIL, password: LOCKOUT_PASSWORD, full_name: 'E2E Lockout Tester' },
      });
      // 201 = created, 409 = already exists — both are fine
    } finally {
      await ctx.dispose();
    }
  });

  test.afterAll(async () => {
    const token = await getAPIToken();
    const ctx = await request.newContext();
    try {
      await ctx.patch(`${API}/auth/admin/unlock`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { email: LOCKOUT_EMAIL },
      });
    } finally {
      await ctx.dispose();
    }
  });

  test('account locks out after N failed login attempts', async ({ page }) => {
    await page.goto('/login');
    const emailInput = page.getByPlaceholder('you@example.com');
    const passwordInput = page.locator('#login-password');
    const signInBtn = page.getByRole('button', { name: 'Sign In' });
    const alert = page.getByRole('alert');

    // Submit wrong password LOCKOUT_THRESHOLD times to build up the counter
    for (let i = 0; i < LOCKOUT_THRESHOLD; i++) {
      await emailInput.fill(LOCKOUT_EMAIL);
      await passwordInput.fill(WRONG_PASSWORD);
      await signInBtn.click();
      await expect(alert).toContainText('Invalid email or password', { timeout: 10_000 });
    }

    // One more attempt triggers the 429 lockout response
    await emailInput.fill(LOCKOUT_EMAIL);
    await passwordInput.fill(WRONG_PASSWORD);
    await signInBtn.click();

    // UI shows the countdown banner
    await expect(alert).toContainText('Account locked', { timeout: 10_000 });
    await expect(alert).toContainText('Try again in');

    // Correct password also fails while account is locked
    await emailInput.fill(LOCKOUT_EMAIL);
    await passwordInput.fill(LOCKOUT_PASSWORD);
    await signInBtn.click();
    await page.waitForResponse((resp) => resp.url().includes('/auth/login'));
    await expect(alert).toContainText('Account locked');
    await expect(page).toHaveURL(/\/login/);
  });
});
