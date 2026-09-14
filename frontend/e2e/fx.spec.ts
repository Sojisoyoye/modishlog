import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaAPI, getAPIToken } from './helpers/auth';

// ---------------------------------------------------------------------------
// FX Rates Page E2E Tests
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();

  // Pre-warm the USDNGN forecast once, up front. Without this, the FIRST
  // /fx page load in the whole run finds no forecast rows, the page
  // auto-triggers generateForecast(), and on a fresh test DB that fails
  // outright ("Insufficient rate data ... have 1 days, need 30") -- so the
  // forecast table (and its pagination controls) never renders for any
  // test in this file. Seed 35 days of synthetic history first so the
  // generate call actually succeeds.
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const headers = { Authorization: `Bearer ${token}` };
    for (let i = 35; i >= 1; i--) {
      const timestamp = new Date(Date.now() - i * 24 * 60 * 60 * 1000).toISOString();
      const rate = 1500 + Math.sin(i / 3) * 20; // mild variation, not flat -- avoids a zero-volatility edge case in the GBM fit
      await ctx.post('http://localhost:8000/api/v1/fx/rates/ingest', {
        headers,
        data: { pair: 'USDNGN', rate, source: 'manual', timestamp },
      });
    }
    await ctx.post('http://localhost:8000/api/v1/fx/forecast/generate', {
      headers,
      data: { pair: 'USDNGN', horizon_days: 180, num_simulations: 10000 },
    });
  } finally {
    await ctx.dispose();
  }
});

test.beforeEach(async ({ page }) => {
  await loginViaAPI(page);
  await page.goto('/fx');
  await expect(page.getByRole('heading', { name: 'FX Rates' })).toBeVisible({ timeout: 15000 });
});

test.describe('FX page layout', () => {
  test('displays the page heading and subtitle', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'FX Rates' })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Track and forecast NGN exchange rates')).toBeVisible();
  });

  test('displays the USD/NGN rate card', async ({ page }) => {
    await expect(page.getByText('USD / NGN').first()).toBeVisible();
  });

  test('displays the Add Rate form', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Add Rate' })).toBeVisible();
  });

  test('displays the Historical Rates chart section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Historical Rates (90 days)' })).toBeVisible();
  });

  test('displays the 30-Day Forecast section', async ({ page }) => {
    // The forecast heading is dynamic (defaults to 180-Day Forecast)
    await expect(page.locator('h3').filter({ hasText: /\d+-Day Forecast/ })).toBeVisible();
  });
});

test.describe('EUR/NGN rate card', () => {
  // The component no longer has a standalone "EUR/USD Rate" card -- EUR/USD
  // is used internally to derive the EUR/NGN card's value (see
  // fx-page.component.ts, "Derived from USD/NGN x EUR/USD"), not displayed
  // on its own.
  test('shows EUR / NGN label in the rate card', async ({ page }) => {
    await expect(page.getByText('EUR / NGN').first()).toBeVisible();
  });

  test('shows a EUR/NGN rate value or a load-history fallback message', async ({ page }) => {
    const card = page.getByTestId('eur-ngn-rate-card');
    const hasValue = await card
      .getByText(/^₦[\d,]+\.\d{2}$/)
      .isVisible()
      .catch(() => false);
    const hasFallback = await card.getByText('Load history to populate').isVisible().catch(() => false);
    expect(hasValue || hasFallback).toBeTruthy();
  });
});

test.describe('Add Rate form', () => {
  test('pair selector has USDNGN and EURUSD options', async ({ page }) => {
    // The pair select is the first select in the Add Rate section
    const addRateSection = page.locator('div').filter({ hasText: /^Add Rate$/ }).locator('..');
    const pairSelect = page.locator('select').first();
    await expect(pairSelect).toBeVisible();

    // Check options
    const options = pairSelect.locator('option');
    const texts = await options.allTextContents();
    expect(texts.some((t) => t.includes('USD/NGN'))).toBeTruthy();
    expect(texts.some((t) => t.includes('EUR/USD'))).toBeTruthy();
  });

  test('has Rate, Date, Source inputs and Add button', async ({ page }) => {
    // Rate input
    const rateInput = page.locator('input[type="number"]').first();
    await expect(rateInput).toBeVisible();

    // Date input
    const dateInput = page.locator('input[type="date"]').first();
    await expect(dateInput).toBeVisible();

    // Source select
    const sourceSelect = page.locator('select').nth(1);
    await expect(sourceSelect).toBeVisible();
    const sourceOptions = await sourceSelect.locator('option').allTextContents();
    expect(sourceOptions.some((t) => t.includes('Manual'))).toBeTruthy();
    expect(sourceOptions.some((t) => t.includes('Parallel Market'))).toBeTruthy();

    // Add button
    await expect(page.getByTestId('fx-add-rate-button')).toBeVisible();
  });

  test('selecting EURUSD pair changes rate placeholder', async ({ page }) => {
    const pairSelect = page.locator('select').first();
    await pairSelect.selectOption('EURUSD');

    // The placeholder should change to something like "e.g. 1.08"
    const rateInput = page.locator('input[type="number"]').first();
    await expect(rateInput).toHaveAttribute('placeholder', 'e.g. 1.08');
  });

  test('selecting USDNGN pair shows NGN placeholder', async ({ page }) => {
    const pairSelect = page.locator('select').first();
    await pairSelect.selectOption('USDNGN');

    const rateInput = page.locator('input[type="number"]').first();
    await expect(rateInput).toHaveAttribute('placeholder', 'e.g. 1500');
  });
});

test.describe('Add Rate submission', () => {
  const API = 'http://localhost:8000/api/v1';
  let submittedRateId: string | null = null;

  test.afterEach(async () => {
    if (submittedRateId) {
      const token = await getAPIToken();
      const ctx = await request.newContext();
      try {
        await ctx.delete(`${API}/fx/rates/${submittedRateId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
      } finally {
        await ctx.dispose();
        submittedRateId = null;
      }
    }
  });

  test('submitting a new FX rate shows success toast and updates the current rate card', async ({ page }) => {
    // outer beforeEach already logged in and navigated to /fx

    // Select USDNGN pair
    await page.locator('select#fx-manual-pair').selectOption('USDNGN');

    // Enter rate value
    await page.locator('input#fx-manual-rate').fill('1580');

    // Set source to Manual
    await page.locator('select#fx-manual-source').selectOption('MANUAL');

    // Set date to today
    const today = new Date().toISOString().split('T')[0];
    await page.locator('input#fx-manual-date').fill(today);

    // Intercept the ingest API response to capture the rate ID for cleanup
    const [ingestResponse] = await Promise.all([
      page.waitForResponse((resp) => resp.url().includes('/fx/rates/ingest') && resp.status() === 201),
      page.getByTestId('fx-add-rate-button').click(),
    ]);

    const rateData = await ingestResponse.json();
    submittedRateId = rateData.id;

    // Assert success toast appears
    await expect(page.getByText('Added')).toBeVisible();
    await expect(page.getByText('USDNGN rate recorded')).toBeVisible();

    // Assert the current rate card updates to show the submitted rate.
    // Scoped to the rate card specifically -- the Forecast Insight Panel's
    // "Today (actual)" milestone box can independently show the same value.
    await expect(page.getByTestId('usd-ngn-rate-card').getByText('₦1,580.00')).toBeVisible();
  });

  test('30-Day Forecast section is visible and shows the forecast chart', async ({ page }) => {
    // outer beforeEach already logged in and navigated to /fx

    // The forecast section heading is dynamic (N-Day Forecast)
    await expect(page.locator('h3').filter({ hasText: /\d+-Day Forecast/ })).toBeVisible();

    // The forecast p-chart is the second canvas on the page (index 1); historical chart is first
    await expect(page.locator('canvas').nth(1)).toBeVisible();
  });
});

test.describe('Forecast table pagination', () => {
  test('rows-per-page selector shows 10, 25, 50 options', async ({ page }) => {
    await expect(page.getByRole('button', { name: '10' })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole('button', { name: '25' })).toBeVisible();
    await expect(page.getByRole('button', { name: '50' })).toBeVisible();
  });

  test('clicking 25 rows/page keeps the forecast table visible', async ({ page }) => {
    await page.getByRole('button', { name: '25' }).click();
    // Table must still be present after switching page size
    await expect(page.locator('table').first()).toBeVisible({ timeout: 10_000 });
  });

  test('clicking 50 rows/page keeps the forecast table visible', async ({ page }) => {
    await page.getByRole('button', { name: '50' }).click();
    await expect(page.locator('table').first()).toBeVisible({ timeout: 10_000 });
  });
});
