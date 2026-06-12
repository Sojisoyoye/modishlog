import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI, E2E_EMAIL, E2E_PASSWORD } from './helpers/auth';

// ---------------------------------------------------------------------------
// JWT Token Storage E2E Tests
// Verifies that tokens are NOT stored in localStorage (HttpOnly cookie flow).
// ---------------------------------------------------------------------------

const API = 'http://localhost:8000/api/v1';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Login uses HttpOnly cookie — not localStorage', () => {
  test('after login, localStorage contains no access token', async ({ page }) => {
    await loginViaUI(page);
    await page.waitForURL('**/dashboard', { timeout: 15_000 });

    const accessToken = await page.evaluate(() => localStorage.getItem('modishlog_token'));
    const refreshToken = await page.evaluate(() =>
      localStorage.getItem('modishlog_refresh_token'),
    );
    expect(accessToken).toBeNull();
    expect(refreshToken).toBeNull();
  });

  test('after login, user is authenticated and dashboard is accessible', async ({ page }) => {
    await loginViaUI(page);
    await expect(page).toHaveURL(/\/dashboard/);
  });
});

test.describe('Logout clears session', () => {
  test('logout redirects to /login and localStorage remains empty', async ({ page }) => {
    await loginViaUI(page);

    await page.getByRole('button', { name: 'Logout' }).click();
    await page.waitForURL('**/login', { timeout: 10_000 });
    await expect(page).toHaveURL(/\/login/);

    // localStorage was never populated; confirm it is still empty after logout
    const accessToken = await page.evaluate(() => localStorage.getItem('modishlog_token'));
    expect(accessToken).toBeNull();
  });
});

test.describe('Session guard falls back to cookie on page refresh', () => {
  test('navigating directly to a protected route redirects to /login when unauthenticated', async ({
    page,
  }) => {
    // No login — no cookie — guard must redirect to login
    await page.goto('/dashboard');
    await page.waitForURL('**/login', { timeout: 10_000 });
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('Refresh token endpoint', () => {
  test('POST /auth/refresh returns new access_token with valid refresh token', async ({
    request,
  }) => {
    const loginResp = await request.post(`${API}/auth/login`, {
      data: { email: E2E_EMAIL, password: E2E_PASSWORD },
    });
    expect(loginResp.ok()).toBeTruthy();
    const { refresh_token } = await loginResp.json();
    expect(refresh_token).toBeTruthy();

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
    const loginResp = await request.post(`${API}/auth/login`, {
      data: { email: E2E_EMAIL, password: E2E_PASSWORD },
    });
    const { refresh_token } = await loginResp.json();

    const logoutResp = await request.post(`${API}/auth/logout`, {
      data: { refresh_token },
    });
    expect(logoutResp.ok()).toBeTruthy();

    const refreshResp = await request.post(`${API}/auth/refresh`, {
      data: { refresh_token },
    });
    expect(refreshResp.status()).toBe(401);
  });

  test('POST /auth/logout without refresh token still returns 200', async ({ request }) => {
    const resp = await request.post(`${API}/auth/logout`, {
      data: {},
    });
    expect(resp.ok()).toBeTruthy();
  });
});
