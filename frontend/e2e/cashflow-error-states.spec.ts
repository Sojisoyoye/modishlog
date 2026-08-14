import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

// ---------------------------------------------------------------------------
// Task 193 — /cash-runway and /dscr fetch failures must show a visible error
// state, not the component's initial placeholder signal values ("0.0
// months" / "0.00" / "UNKNOWN"), which look like plausible real data. Uses
// route interception (not the real backend) since there's no clean way to
// force a real 500 from a healthy backend/business.
//
// This is its own file (not appended to cashflow.spec.ts) because the route
// must be registered *before* the page's first navigation, and
// cashflow.spec.ts's shared beforeEach already navigates to /cashflow
// before any test body runs.
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Cashflow page — liquidity fetch failure shows a visible error state (Task 193)', () => {
  test('shows an error banner, not misleading placeholder data, when /cash-runway and /dscr fail', async ({
    page,
  }) => {
    // Register routes BEFORE logging in — loginViaUI navigates through
    // /dashboard first, whose Cash Health card also calls /cash-runway and
    // /dscr. Registering after login would leave that first dashboard call
    // unintercepted, hitting the real backend and (since task 191)
    // generating a real, empty-data projection that gets cached for the
    // rest of the day and pollutes cashflow.spec.ts's own tests depending
    // on file run order. Also stub /projection itself for the same reason.
    await page.route('**/api/v1/cashflow/projection', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"monthly_buckets":[]}' })
    );
    await page.route('**/api/v1/cashflow/cash-runway', (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"error"}' })
    );
    await page.route('**/api/v1/cashflow/dscr', (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"error"}' })
    );

    await loginViaUI(page);
    await page.goto('/cashflow');
    await expect(page.getByRole('heading', { name: 'Cashflow' })).toBeVisible({ timeout: 10_000 });

    // The misleading placeholder values must never render as if real data.
    await expect(page.getByText('0.0 months', { exact: true })).not.toBeVisible();
    await expect(page.getByText('UNKNOWN', { exact: true })).not.toBeVisible();

    // A visible, distinct error state must appear instead.
    await expect(page.getByText(/failed to load/i)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: /retry/i })).toBeVisible();
  });

  test('Retry re-fetches and shows real data once the backend recovers', async ({ page }) => {
    // See the comment in the previous test — routes must be registered
    // before loginViaUI, not after, since the dashboard it navigates
    // through also calls /cash-runway and /dscr.
    //
    // The "recovered" response is a synthetic fulfill(), not
    // route.continue() to the real backend — this test only needs to prove
    // the component re-fetches and clears its error state, not re-verify
    // backend correctness (covered elsewhere). Using the real backend here
    // would also trigger a real projection generation (task 191's daily
    // cache), leaking state into cashflow.spec.ts's tests depending on file
    // run order.
    await page.route('**/api/v1/cashflow/projection', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"monthly_buckets":[]}' })
    );
    let shouldFail = true;
    await page.route('**/api/v1/cashflow/cash-runway', (route) =>
      shouldFail
        ? route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
        : route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              runway_months: '6.0',
              runway_months_is_finite: true,
              avg_monthly_burn: '10000.00',
              runway_trend: null,
            }),
          })
    );
    await page.route('**/api/v1/cashflow/dscr', (route) =>
      shouldFail
        ? route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
        : route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              dscr: '2.500',
              dscr_is_finite: true,
              net_operating_income: '25000.00',
              total_debt_service: '10000.00',
              color: 'green',
              dscr_trend: null,
            }),
          })
    );

    await loginViaUI(page);
    await page.goto('/cashflow');
    await expect(page.getByText(/failed to load/i)).toBeVisible({ timeout: 10_000 });

    shouldFail = false;
    await page.getByRole('button', { name: /retry/i }).click();

    await expect(page.getByText(/failed to load/i)).not.toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('Cash Runway').first()).toBeVisible();
  });
});
