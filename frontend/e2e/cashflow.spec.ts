import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { createOperatingCost, createLoan } from './helpers/data';

// ---------------------------------------------------------------------------
// Cashflow Page E2E Tests
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
  // Seed an operating cost so the 6-month projection has non-zero outflows
  await createOperatingCost('E2E Monthly Rent', '50000.00', 'monthly', 'rent');
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/cashflow');
  await page.waitForLoadState('domcontentloaded');
  await expect(page.getByRole('heading', { name: 'Cashflow' })).toBeVisible({ timeout: 10_000 });
});

test.describe('Cashflow page layout', () => {
  test('displays the page heading and subtitle', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Cashflow' })).toBeVisible();
    await expect(
      page.getByText('Monitor liquidity and project future cashflows'),
    ).toBeVisible();
  });

  test('displays Cash Runway metric with a numeric value or a friendly no-burn state', async ({
    page,
  }) => {
    await expect(page.getByText('Cash Runway').first()).toBeVisible();
    // Task 187 — an account with no burn shows a friendly indicator instead
    // of a raw "999.0 months" sentinel; only a real burn rate shows "X.X
    // months" (days / 30, 1 decimal).
    await expect(
      page.getByText(/\d+\.\d\s*months/).or(page.getByText(/no burn/i)).first(),
    ).toBeVisible({ timeout: 10_000 });
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

  test('6-Month Projection table has at least one row with non-zero outflows', async ({
    page,
  }) => {
    // With E2E Monthly Rent seeded, outflows > 0 for each month
    const tableBody = page.locator('table').filter({ hasText: /Month/i }).locator('tbody');
    await expect(tableBody.locator('tr').first()).toBeVisible({ timeout: 10_000 });

    // First row should have a month label (e.g. "2026-07" or "Jul 2026")
    const firstRowCells = tableBody.locator('tr').first().locator('td');
    const monthText = await firstRowCells.first().textContent();
    expect((monthText ?? '').trim().length).toBeGreaterThan(0);

    // Outflows cell (3rd column) should show a non-zero currency value
    const outflowsText = await firstRowCells.nth(2).textContent();
    const outflowsNum = parseFloat((outflowsText ?? '').replace(/[^0-9.]/g, ''));
    expect(outflowsNum).toBeGreaterThan(0);
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

  test('clicking Simulate shows scenario results with Worst DSCR and Cash Runway', async ({
    page,
  }) => {
    await page.getByRole('button', { name: 'Simulate' }).click();

    // Scenario result panel must appear — no soft catches
    await expect(page.getByText('Worst DSCR')).toBeVisible({ timeout: 15_000 });

    // Task 187 — DSCR value must be a decimal number (e.g. "0.00" or
    // "1.23"), or a friendly "No debt" state if this account has no loan.
    // Use containsText since Angular may add whitespace around the value.
    const dscrValueEl = page
      .locator('p.text-2xl.font-bold')
      .filter({ hasText: /(\d+\.\d{2}|no debt)/i })
      .first();
    await expect(dscrValueEl).toBeVisible({ timeout: 5_000 });

    // Cash Runway in the scenario panel (nth(1) to skip the page-level metric)
    await expect(page.getByText('Cash Runway').nth(1)).toBeVisible();
    // Task 187 — runway value shows "X.X months", or a friendly no-burn
    // state if the stressed scenario is still cash-flow-positive.
    await expect(
      page.getByText(/\d+\.\d\s*months/).or(page.getByText(/no burn/i)).last(),
    ).toBeVisible({ timeout: 5_000 });
  });

  test('preset button "FX +10%" populates the FX Shock field and shows simulation result', async ({
    page,
  }) => {
    await page.getByRole('button', { name: 'FX +10%' }).click();

    // Input must update to 10 via Angular binding
    await expect(page.locator('#cf-fx-shock')).toHaveValue('10');

    // The auto-triggered simulation must produce a visible scenario result panel
    await expect(page.getByText('Worst DSCR')).toBeVisible({ timeout: 30_000 });
  });

  test('preset button "Demand -20%" populates Demand Drop field and shows simulation result', async ({
    page,
  }) => {
    await page.getByRole('button', { name: 'Demand -20%' }).click();

    await expect(page.locator('#cf-demand-drop')).toHaveValue('20');
    await expect(page.getByText('Worst DSCR')).toBeVisible({ timeout: 15_000 });
  });
});

// ---------------------------------------------------------------------------
// Task 187 — 999 sentinel must never leak to the UI as a raw number, and
// the Risk Rating badge must never fall back to "UNKNOWN".
// ---------------------------------------------------------------------------

test.describe('Undefined DSCR/Runway shown as friendly text, not raw 999', () => {
  test('Cash Runway card never shows the raw 999.0 sentinel', async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/cashflow');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByRole('heading', { name: 'Cashflow' })).toBeVisible({ timeout: 10_000 });

    await expect(page.getByText('999.0 months')).not.toBeVisible();
  });

  test('DSCR card never shows the raw 999.00 sentinel when there is no loan', async ({ page }) => {
    // No spec in this suite ever creates a loan obligation, so DSCR is
    // deterministically undefined (no debt-service obligation) here.
    await loginViaUI(page);
    await page.goto('/cashflow');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByRole('heading', { name: 'Cashflow' })).toBeVisible({ timeout: 10_000 });

    await expect(page.getByText('999.00', { exact: true })).not.toBeVisible();
    await expect(page.getByText(/no debt/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test('Risk Rating badge is never shown as UNKNOWN', async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/cashflow');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByRole('heading', { name: 'Cashflow' })).toBeVisible({ timeout: 10_000 });

    await expect(page.getByText('Risk Rating').first()).toBeVisible();
    await expect(page.getByText('UNKNOWN', { exact: true })).not.toBeVisible();
  });

  test('DSCR shows a real numeric ratio once a loan obligation exists', async ({ page }) => {
    await ensureTestUser();
    await createLoan('E2E Sentinel Test Bank', '500000.00', '50000.00');

    await loginViaUI(page);
    await page.goto('/cashflow');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByRole('heading', { name: 'Cashflow' })).toBeVisible({ timeout: 10_000 });

    // A real loan payment exists now — the finite path must still render a
    // genuine ratio, not stay stuck on the 'No debt' friendly text.
    // DSCR is the second "text-3xl font-bold" metric (after Cash Runway).
    const dscrValue = page.locator('p.text-3xl.font-bold').nth(1);
    await expect(dscrValue).toBeVisible({ timeout: 10_000 });
    await expect(dscrValue).toHaveText(/\d+\.\d{2}/);
  });
});
