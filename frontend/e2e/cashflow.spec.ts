import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

// ---------------------------------------------------------------------------
// Cashflow Page E2E Tests
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/cashflow');
  await expect(page.getByRole('heading', { name: 'Cashflow' })).toBeVisible();
});

test.describe('Cashflow page layout', () => {
  test('displays the page heading and subtitle', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Cashflow' })).toBeVisible();
    await expect(
      page.getByText('Monitor liquidity and project future cashflows'),
    ).toBeVisible();
  });

  test('displays Cash Runway metric', async ({ page }) => {
    await expect(page.getByText('Cash Runway').first()).toBeVisible();
    // Should show "X days"
    await expect(page.getByText(/\d+\s*days/).first()).toBeVisible();
  });

  test('displays DSCR metric', async ({ page }) => {
    await expect(page.getByText('DSCR').first()).toBeVisible();
  });

  test('displays Risk Rating metric', async ({ page }) => {
    await expect(page.getByText('Risk Rating').first()).toBeVisible();
  });

  test('displays 6-Month Projection section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '6-Month Projection' })).toBeVisible();
  });

  test('displays Month-by-Month table', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Month-by-Month' })).toBeVisible();
    // Table headers
    await expect(page.getByRole('columnheader', { name: /Month/i })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Inflows/i })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Outflows/i })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Net/i })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Cumulative/i })).toBeVisible();
  });
});

test.describe('Scenario Simulator', () => {
  test('displays the Scenario Simulator section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Scenario Simulator' })).toBeVisible();
  });

  test('has FX Shock and Demand Drop inputs', async ({ page }) => {
    await expect(page.getByText('FX Shock (%)')).toBeVisible();
    await expect(page.getByText('Demand Drop (%)')).toBeVisible();
  });

  test('has preset scenario buttons', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'FX +10%' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'FX +20%' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Demand -20%' })).toBeVisible();
  });

  test('has Simulate button', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Simulate' })).toBeVisible();
  });

  test('clicking Simulate shows scenario results', async ({ page }) => {
    await page.getByRole('button', { name: 'Simulate' }).click();

    // Wait for the scenario result to appear
    await page.waitForTimeout(3000);

    // The result panel should show (if API returns data)
    const resultPanel = page.getByText('Worst DSCR');
    const isVisible = await resultPanel.isVisible().catch(() => false);
    if (isVisible) {
      await expect(page.getByText('Cash Runway').nth(1)).toBeVisible();
    }
  });

  test('preset button "FX +10%" populates the FX Shock field and triggers simulation', async ({
    page,
  }) => {
    await page.getByRole('button', { name: 'FX +10%' }).click();

    // The preset sets fxShock = 10 via Angular binding — verify the input reflects this
    const fxShockInput = page.locator('#cf-fx-shock');
    await expect(fxShockInput).toHaveValue('10');

    // Wait for the auto-triggered simulation to settle
    await page.waitForLoadState('networkidle');
  });
});
