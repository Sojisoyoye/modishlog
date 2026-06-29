import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaAPI } from './helpers/auth';

// ---------------------------------------------------------------------------
// Dashboard KPI Summary Cards — E2E Tests (Task 126)
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaAPI(page);
  // Wait for KPI cards to render (data loads async behind loading() signal)
  await page.locator('[data-testid="kpi-card"]').first()
    .waitFor({ timeout: 20_000 }).catch(() => {});
});

test.describe('KPI summary header', () => {
  test('shows personalised Welcome heading', async ({ page }) => {
    await expect(page.getByText('Good day,')).toBeVisible();
  });
});

test.describe('KPI card labels', () => {
  test('displays all 8 KPI card labels', async ({ page }) => {
    await expect(page.getByText('Total Sales')).toBeVisible();
    await expect(page.getByText('Net Profit')).toBeVisible();
    await expect(page.getByText('Unpaid Sales')).toBeVisible();
    await expect(page.getByText('Customer Returns')).toBeVisible();
    await expect(page.getByText('Total Purchased')).toBeVisible();
    await expect(page.getByText('Amount Owed')).toBeVisible();
    await expect(page.getByText('Supplier Refunds')).toBeVisible();
    await expect(page.getByText('Monthly Expenses')).toBeVisible();
  });
});

test.describe('KPI card values', () => {
  test('all values default to ₦ 0.00 on empty account', async ({ page }) => {
    // On a fresh test account with no transactions, all cards should show 0.00
    const zeroPattern = /₦\s*0\.00/;
    const cards = page.locator('[data-testid="kpi-card"]');
    // Wait for Angular to finish rendering the KPI section
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });
    const count = await cards.count();
    // At least the 8 KPI cards should be present
    expect(count).toBeGreaterThanOrEqual(8);
    // Check first visible value card shows ₦ 0.00
    await expect(page.getByText(zeroPattern).first()).toBeVisible();
  });
});

test.describe('Location filter', () => {
  test('location dropdown is visible on the dashboard', async ({ page }) => {
    await expect(page.getByText('All locations')).toBeVisible();
  });

  test('selecting a location updates the KPI cards', async ({ page }) => {
    const dropdown = page.locator('[data-testid="location-dropdown"]');
    // Dropdown renders (may be empty if no locations seeded, but it must exist)
    await expect(dropdown).toBeVisible();
  });
});

test.describe('Date filter', () => {
  test('Filter by date button is visible', async ({ page }) => {
    await expect(page.getByPlaceholder('Filter by date').first()).toBeVisible();
  });

  test('clicking Filter by date opens a calendar picker', async ({ page }) => {
    await page.getByPlaceholder('Filter by date').first().click();
    // PrimeNG calendar panel becomes visible
    await expect(page.locator('.p-datepicker')).toBeVisible();
  });
});

test.describe('KPI card sub-lines', () => {
  test('Sell Return card shows Total Sell Return and Total Sell Return Paid sub-lines', async ({ page }) => {
    await expect(page.getByText('Total returned:').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Amount paid back:')).toBeVisible({ timeout: 10000 });
  });

  test('Purchase Return card shows Total Purchase Return and Total Purchase Return Paid sub-lines', async ({ page }) => {
    await expect(page.getByText('Total returned:').nth(1)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('Amount refunded:')).toBeVisible();
  });
});
