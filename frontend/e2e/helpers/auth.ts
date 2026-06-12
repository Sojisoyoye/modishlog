import { Page, request } from '@playwright/test';

const API = 'http://localhost:8000/api/v1';
export const E2E_EMAIL = 'e2e-suite@modishlogtest.com';
export const E2E_PASSWORD = 'E2eTest!1234';

/**
 * Register the test user (idempotent -- 409 Conflict is expected on re-runs).
 */
export async function ensureTestUser(): Promise<void> {
  const ctx = await request.newContext();
  try {
    await ctx.post(`${API}/auth/register`, {
      data: { email: E2E_EMAIL, password: E2E_PASSWORD, full_name: 'E2E Tester' },
    });
    // 201 = created, 409 = already exists -- both are fine
  } finally {
    await ctx.dispose();
  }
}

/**
 * Log in via the UI login form so Angular's AuthService sets the token properly.
 * After this call the page is on /dashboard and the auth session is active.
 */
export async function loginViaUI(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByPlaceholder('you@example.com').fill(E2E_EMAIL);
  await page.locator('input[type="password"]').fill(E2E_PASSWORD);
  await page.getByRole('button', { name: 'Sign In' }).click();
  // After successful login, Angular navigates to / -> redirected to /dashboard
  await page.waitForURL('**/dashboard', { timeout: 15_000 });
}

/**
 * Log in via the API using the page's browser context so the HttpOnly
 * access_token cookie is stored in the same context the page uses.
 * The auth guard then restores the session via /auth/me + cookie on navigation.
 * Use when you need auth but don't need to test the login form itself.
 */
export async function loginViaAPI(page: Page): Promise<void> {
  await page.context().request.post(`${API}/auth/login`, {
    data: { email: E2E_EMAIL, password: E2E_PASSWORD },
  });
  // Navigate directly — the auth guard restores the session via /auth/me + cookie.
  await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
  await page.waitForURL('**/dashboard', { timeout: 15_000 });
}

/**
 * Obtain a raw API token (for API-level assertions).
 */
export async function getAPIToken(): Promise<string> {
  const ctx = await request.newContext();
  try {
    const resp = await ctx.post(`${API}/auth/login`, {
      data: { email: E2E_EMAIL, password: E2E_PASSWORD },
    });
    const { access_token } = await resp.json();
    return access_token;
  } finally {
    await ctx.dispose();
  }
}
