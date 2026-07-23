import { Page, request } from '@playwright/test';

const API = 'http://localhost:8000/api/v1';
export const E2E_EMAIL = 'e2e-suite@modishlogtest.com';
export const E2E_PASSWORD = 'E2eTest!1234';

/**
 * Create the test user's business + owner account (idempotent -- 409
 * Conflict is expected on re-runs).
 *
 * POST /auth/register requires an already-authenticated admin (it's for
 * adding staff to an existing business, not self-serve signup) -- it always
 * 401s here and was silently ignored, so the E2E test user was never
 * actually created against a fresh CI database and every login-dependent
 * test failed. POST /auth/onboard is the real public signup endpoint
 * (creates a Business + owner User atomically).
 */
export async function ensureTestUser(): Promise<void> {
  const ctx = await request.newContext();
  try {
    await ctx.post(`${API}/auth/onboard`, {
      data: {
        full_name: 'E2E Tester',
        email: E2E_EMAIL,
        password: E2E_PASSWORD,
        business_name: 'E2E Test Business',
        ndpr_consent: true,
      },
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
  await page.waitForURL('**/dashboard', { timeout: 20_000 });
}

/**
 * Log in via the API using the page's browser context so the HttpOnly
 * access_token cookie is stored in the same context the page uses.
 * The auth guard then restores the session via /auth/me + cookie on navigation.
 * Use when you need auth but don't need to test the login form itself.
 */
export async function loginViaAPI(page: Page): Promise<void> {
  // Retry on network-level failures (connection refused, timeout) but not HTTP errors.
  // Auth lockout tests can briefly saturate the backend causing transient drops.
  for (let attempt = 1; attempt <= 3; attempt++) {
    let resp: Awaited<ReturnType<typeof page.context['request']['post']>>;
    try {
      resp = await page.context().request.post(`${API}/auth/login`, {
        data: { email: E2E_EMAIL, password: E2E_PASSWORD },
      });
    } catch (err) {
      // Network error (not an HTTP error) — retry with backoff
      if (attempt === 3) throw err;
      await new Promise(r => setTimeout(r, attempt * 1000));
      continue;
    }
    // HTTP errors (401, 429, 5xx) should not be silently retried
    if (!resp.ok()) {
      throw new Error(`loginViaAPI failed: HTTP ${resp.status()} — ${await resp.text()}`);
    }
    break;
  }
  // Navigate directly — the auth guard restores the session via /auth/me + cookie.
  await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
  await page.waitForURL('**/dashboard', { timeout: 20_000 });
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
