import { test, expect, request as pwRequest } from '@playwright/test';

const API = 'http://localhost:8000/api/v1';
// Unique email per test run to avoid duplicate-email conflicts
const REG_EMAIL = `e2e-register-${Date.now()}@modishlogtest.com`;
const REG_PASSWORD = 'E2eReg!5678';
const REG_NAME = 'E2E Register Tester';
const REG_BUSINESS = 'E2E Test Shop';

// ---------------------------------------------------------------------------
// Registration Page E2E Tests
// ---------------------------------------------------------------------------

test.describe('Register page — step 1 form renders', () => {
  test('displays name, email, password and confirm-password inputs', async ({ page }) => {
    await page.goto('/register');
    await expect(page.locator('#reg-full-name')).toBeVisible();
    await expect(page.locator('#reg-email')).toBeVisible();
    await expect(page.locator('#reg-password')).toBeVisible();
    await expect(page.locator('#reg-confirm-password')).toBeVisible();
  });

  test('displays "1 · Account" step pill as active on load', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByText('1 · Account')).toBeVisible();
  });

  test('displays Next button on step 1', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByRole('button', { name: /next/i })).toBeVisible();
  });
});

test.describe('Register page — step navigation', () => {
  test('Next button advances to step 2 when step 1 fields are valid', async ({ page }) => {
    await page.goto('/register');

    await page.locator('#reg-full-name').fill(REG_NAME);
    await page.locator('#reg-email').fill(`step2-${Date.now()}@modishlogtest.com`);
    await page.locator('#reg-password').fill(REG_PASSWORD);
    await page.locator('#reg-confirm-password').fill(REG_PASSWORD);

    await page.getByRole('button', { name: /next/i }).click();

    // Step 2 should show business_name input
    await expect(page.locator('#reg-business-name')).toBeVisible({ timeout: 5_000 });
  });

  test('Back button on step 2 returns to step 1', async ({ page }) => {
    await page.goto('/register');

    // Fill and advance to step 2
    await page.locator('#reg-full-name').fill(REG_NAME);
    await page.locator('#reg-email').fill(`back-${Date.now()}@modishlogtest.com`);
    await page.locator('#reg-password').fill(REG_PASSWORD);
    await page.locator('#reg-confirm-password').fill(REG_PASSWORD);
    await page.getByRole('button', { name: /next/i }).click();

    // Wait for step 2 to appear
    await expect(page.locator('#reg-business-name')).toBeVisible({ timeout: 5_000 });

    // Click Back
    await page.getByRole('button', { name: /back/i }).click();

    // Step 1 inputs should be visible again
    await expect(page.locator('#reg-full-name')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('#reg-email')).toBeVisible();
  });

  test('Next button shows error when required fields are empty', async ({ page }) => {
    await page.goto('/register');
    await page.getByRole('button', { name: /next/i }).click();
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 5_000 });
  });

  test('Next button shows error when passwords do not match', async ({ page }) => {
    await page.goto('/register');

    await page.locator('#reg-full-name').fill(REG_NAME);
    await page.locator('#reg-email').fill(`mismatch-${Date.now()}@modishlogtest.com`);
    await page.locator('#reg-password').fill(REG_PASSWORD);
    await page.locator('#reg-confirm-password').fill('WrongConfirm!999');

    await page.getByRole('button', { name: /next/i }).click();
    await expect(page.getByText(/passwords do not match/i)).toBeVisible({ timeout: 5_000 });
  });
});

test.describe('Register page — full happy path', () => {
  test('submitting both steps with valid data redirects to /dashboard', async ({ page }) => {
    // Use a unique email to avoid duplicate conflicts
    const uniqueEmail = `e2e-happy-${Date.now()}@modishlogtest.com`;

    await page.goto('/register');

    // Step 1
    await page.locator('#reg-full-name').fill(REG_NAME);
    await page.locator('#reg-email').fill(uniqueEmail);
    await page.locator('#reg-password').fill(REG_PASSWORD);
    await page.locator('#reg-confirm-password').fill(REG_PASSWORD);
    await page.getByRole('button', { name: /next/i }).click();

    // Step 2
    await expect(page.locator('#reg-business-name')).toBeVisible({ timeout: 5_000 });
    await page.locator('#reg-business-name').fill(REG_BUSINESS);

    await page.getByRole('button', { name: /create account/i }).click();

    // Should redirect to dashboard after successful registration
    await page.waitForURL('**/dashboard', { timeout: 20_000 });
    await expect(page).toHaveURL(/\/dashboard/);
  });
});

test.describe('Register page — duplicate email error', () => {
  test('shows error message when registering with an already-registered email', async ({ page }) => {
    // First, create a user via the API
    const duplicateEmail = `e2e-dup-${Date.now()}@modishlogtest.com`;
    const ctx = await pwRequest.newContext();
    try {
      // Register via the onboard endpoint first
      await ctx.post(`${API}/auth/onboard`, {
        data: {
          full_name: REG_NAME,
          email: duplicateEmail,
          password: REG_PASSWORD,
          business_name: 'First Shop',
          currency: 'NGN',
          timezone: 'Africa/Lagos',
          fiscal_year_start_month: 1,
        },
      });
    } finally {
      await ctx.dispose();
    }

    // Now try to register with the same email via the UI
    await page.goto('/register');

    await page.locator('#reg-full-name').fill(REG_NAME);
    await page.locator('#reg-email').fill(duplicateEmail);
    await page.locator('#reg-password').fill(REG_PASSWORD);
    await page.locator('#reg-confirm-password').fill(REG_PASSWORD);
    await page.getByRole('button', { name: /next/i }).click();

    await expect(page.locator('#reg-business-name')).toBeVisible({ timeout: 5_000 });
    await page.locator('#reg-business-name').fill(REG_BUSINESS);
    await page.getByRole('button', { name: /create account/i }).click();

    // Error message should appear
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 10_000 });
    // Should NOT navigate away
    await expect(page).toHaveURL(/\/register/);
  });
});

test.describe('Register page — footer link', () => {
  test('shows a link to /login', async ({ page }) => {
    await page.goto('/register');
    const loginLink = page.getByRole('link', { name: /log in/i });
    await expect(loginLink).toBeVisible();
    await expect(loginLink).toHaveAttribute('href', '/login');
  });
});
