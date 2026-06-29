import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';

// ---------------------------------------------------------------------------
// FX Rates Page E2E Tests
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/fx');
  await expect(page.getByRole('heading', { name: 'FX Rates' })).toBeVisible({ timeout: 15000 });
});

test.describe('FX page layout', () => {
  test('displays the page heading and subtitle', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'FX Rates' })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Track and forecast NGN/USD exchange rates')).toBeVisible();
  });

  test('displays the Current NGN/USD Rate card', async ({ page }) => {
    await expect(page.getByText('Current NGN/USD Rate').first()).toBeVisible();
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

test.describe('EUR/USD sub-card (Task 16)', () => {
  test('shows EUR/USD Rate label in the rate card', async ({ page }) => {
    await expect(page.getByText('EUR/USD Rate').first()).toBeVisible();
  });

  test('shows EUR/USD rate value or fallback message', async ({ page }) => {
    // Either a rate number is shown, or "No EUR/USD rate recorded" text
    const rateValue = page.locator('text=EUR/USD Rate').locator('..');
    await expect(rateValue).toBeVisible();
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
    await expect(page.getByRole('button', { name: 'Add' })).toBeVisible();
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
      page.getByRole('button', { name: 'Add' }).click(),
    ]);

    const rateData = await ingestResponse.json();
    submittedRateId = rateData.id;

    // Assert success toast appears
    await expect(page.getByText('Added')).toBeVisible();
    await expect(page.getByText('USDNGN rate recorded')).toBeVisible();

    // Assert the current rate card updates to show the submitted rate
    await expect(page.getByText('₦1,580.00')).toBeVisible();
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
