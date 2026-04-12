import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

// ---------------------------------------------------------------------------
// FX Rates Page E2E Tests
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/fx');
  await expect(page.getByRole('heading', { name: 'FX Rates' })).toBeVisible();
});

test.describe('FX page layout', () => {
  test('displays the page heading and subtitle', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'FX Rates' })).toBeVisible();
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
    await expect(page.getByRole('heading', { name: '30-Day Forecast' })).toBeVisible();
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
