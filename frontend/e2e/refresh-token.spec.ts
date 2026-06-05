import { test, expect } from '@playwright/test';
import { ensureTestUser, E2E_EMAIL, E2E_PASSWORD } from './helpers/auth';

// ---------------------------------------------------------------------------
// JWT Refresh Token E2E Tests
// ---------------------------------------------------------------------------

const API = 'http://localhost:8000/api/v1';
const TOKEN_KEY = 'modishlog_token';
const REFRESH_TOKEN_KEY = 'modishlog_refresh_token';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Login stores refresh token', () => {
  test('login response stores both access_token and refresh_token in localStorage', async ({
    page,
  }) => {
    await page.goto('/login');
    await page.getByPlaceholder('you@example.com').fill(E2E_EMAIL);
    await page.locator('input[type="password"]').fill(E2E_PASSWORD);
    await page.getByRole('button', { name: 'Sign In' }).click();

    await page.waitForURL('**/dashboard', { timeout: 15_000 });

    const accessToken = await page.evaluate((key) => localStorage.getItem(key), TOKEN_KEY);
    const refreshToken = await page.evaluate((key) => localStorage.getItem(key), REFRESH_TOKEN_KEY);

    expect(accessToken).toBeTruthy();
    expect(refreshToken).toBeTruthy();
  });
});

test.describe('Logout revokes refresh token', () => {
  test('logout clears both tokens from localStorage', async ({ page }) => {
    // Log in first
    await page.goto('/login');
    await page.getByPlaceholder('you@example.com').fill(E2E_EMAIL);
    await page.locator('input[type="password"]').fill(E2E_PASSWORD);
    await page.getByRole('button', { name: 'Sign In' }).click();
    await page.waitForURL('**/dashboard', { timeout: 15_000 });

    // Verify tokens exist
    const refreshTokenBefore = await page.evaluate(
      (key) => localStorage.getItem(key),
      REFRESH_TOKEN_KEY,
    );
    expect(refreshTokenBefore).toBeTruthy();

    // Click logout
    await page.getByRole('button', { name: 'Logout' }).click();
    await page.waitForURL('**/login', { timeout: 10_000 });

    // Verify tokens are cleared
    const accessTokenAfter = await page.evaluate((key) => localStorage.getItem(key), TOKEN_KEY);
    const refreshTokenAfter = await page.evaluate(
      (key) => localStorage.getItem(key),
      REFRESH_TOKEN_KEY,
    );
    expect(accessTokenAfter).toBeNull();
    expect(refreshTokenAfter).toBeNull();
  });
});

test.describe('Silent refresh on 401', () => {
  test('interceptor silently refreshes expired access token and retries request', async ({
    page,
  }) => {
    // Log in to get a valid refresh token
    await page.goto('/login');
    await page.getByPlaceholder('you@example.com').fill(E2E_EMAIL);
    await page.locator('input[type="password"]').fill(E2E_PASSWORD);
    await page.getByRole('button', { name: 'Sign In' }).click();
    await page.waitForURL('**/dashboard', { timeout: 15_000 });

    const refreshToken = await page.evaluate((key) => localStorage.getItem(key), REFRESH_TOKEN_KEY);
    expect(refreshToken).toBeTruthy();

    // Simulate an expired access token by replacing it with an invalid value
    await page.evaluate((key) => localStorage.setItem(key, 'expired-invalid-token'), TOKEN_KEY);

    // Navigate to a protected route -- the interceptor should silently refresh
    await page.goto('/dashboard');

    // The page should remain on /dashboard (not redirect to /login)
    // because the interceptor retried the request after obtaining a new access token
    await page.waitForTimeout(3_000);
    await expect(page).toHaveURL(/\/dashboard/);

    // The access token should have been updated to a new valid one
    const newAccessToken = await page.evaluate((key) => localStorage.getItem(key), TOKEN_KEY);
    expect(newAccessToken).toBeTruthy();
    expect(newAccessToken).not.toBe('expired-invalid-token');
  });

  test('redirects to login when refresh token is also invalid', async ({ page }) => {
    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    // Set both tokens to invalid values
    await page.evaluate((key) => localStorage.setItem(key, 'invalid-access-token'), TOKEN_KEY);
    await page.evaluate(
      (key) => localStorage.setItem(key, 'invalid-refresh-token'),
      REFRESH_TOKEN_KEY,
    );

    // Attempt to access a protected route
    await page.goto('/dashboard');

    // Should redirect to login because refresh also fails
    await page.waitForURL('**/login', { timeout: 10_000 });
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('Refresh token endpoint', () => {
  test('POST /auth/refresh returns new access_token with valid refresh token', async ({
    request,
  }) => {
    // First login to get a real refresh token
    const loginResp = await request.post(`${API}/auth/login`, {
      data: { email: E2E_EMAIL, password: E2E_PASSWORD },
    });
    expect(loginResp.ok()).toBeTruthy();
    const { refresh_token } = await loginResp.json();
    expect(refresh_token).toBeTruthy();

    // Use it to get a new access token
    const refreshResp = await request.post(`${API}/auth/refresh`, {
      data: { refresh_token },
    });
    expect(refreshResp.ok()).toBeTruthy();
    const data = await refreshResp.json();
    expect(data.access_token).toBeTruthy();
    expect(data.token_type).toBe('bearer');
  });

  test('POST /auth/refresh returns 401 with invalid refresh token', async ({ request }) => {
    const resp = await request.post(`${API}/auth/refresh`, {
      data: { refresh_token: 'totally-invalid-token' },
    });
    expect(resp.status()).toBe(401);
  });

  test('POST /auth/logout revokes token so subsequent refresh fails', async ({ request }) => {
    // Login to get tokens
    const loginResp = await request.post(`${API}/auth/login`, {
      data: { email: E2E_EMAIL, password: E2E_PASSWORD },
    });
    const { refresh_token } = await loginResp.json();

    // Logout
    const logoutResp = await request.post(`${API}/auth/logout`, {
      data: { refresh_token },
    });
    expect(logoutResp.ok()).toBeTruthy();

    // Try to refresh with the revoked token
    const refreshResp = await request.post(`${API}/auth/refresh`, {
      data: { refresh_token },
    });
    expect(refreshResp.status()).toBe(401);
  });
});
