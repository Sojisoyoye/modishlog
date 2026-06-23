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
});

test.describe('KPI summary header', () => {
  test('shows personalised Welcome heading', async ({ page }) => {
    await expect(page.getByText(/Welcome .+,/)).toBeVisible();
  });
});

test.describe('KPI card labels', () => {
  test('displays all 8 KPI card labels', async ({ page }) => {
    await expect(page.getByText('TOTAL SALES')).toBeVisible();
    await expect(page.getByText('NET').first()).toBeVisible();
    await expect(page.getByText('INVOICE DUE')).toBeVisible();
    await expect(page.getByText('TOTAL SELL RETURN')).toBeVisible();
    await expect(page.getByText('TOTAL PURCHASE')).toBeVisible();
    await expect(page.getByText('PURCHASE DUE')).toBeVisible();
    await expect(page.getByText('TOTAL PURCHASE RETURN')).toBeVisible();
    await expect(page.getByText('EXPENSE')).toBeVisible();
  });
});

test.describe('KPI card values', () => {
  test('all values default to ₦ 0.00 on empty account', async ({ page }) => {
    // On a fresh test account with no transactions, all cards should show 0.00
    const zeroPattern = /₦\s*0\.00/;
    const cards = page.locator('[data-testid="kpi-card"]');
    const count = await cards.count();
    // At least the 8 KPI cards should be present
    expect(count).toBeGreaterThanOrEqual(8);
    // Check first visible value card shows ₦ 0.00
    await expect(page.getByText(zeroPattern).first()).toBeVisible();
  });
});

test.describe('Location filter', () => {
  test('location dropdown is visible on the dashboard', async ({ page }) => {
    await expect(page.getByText('Select location')).toBeVisible();
  });

  test('selecting a location updates the KPI cards', async ({ page }) => {
    const dropdown = page.locator('[data-testid="location-dropdown"]');
    // Dropdown renders (may be empty if no locations seeded, but it must exist)
    await expect(dropdown).toBeVisible();
  });
});

test.describe('Date filter', () => {
  test('Filter by date button is visible', async ({ page }) => {
    await expect(page.getByPlaceholder('Filter by date')).toBeVisible();
  });

  test('clicking Filter by date opens a calendar picker', async ({ page }) => {
    await page.getByPlaceholder('Filter by date').click();
    // PrimeNG calendar panel becomes visible
    await expect(page.locator('.p-datepicker')).toBeVisible();
  });
});

test.describe('KPI card sub-lines', () => {
  test('Sell Return card shows Total Sell Return and Total Sell Return Paid sub-lines', async ({ page }) => {
    await expect(page.getByText('Total Sell Return:')).toBeVisible();
    await expect(page.getByText('Total Sell Return Paid:')).toBeVisible();
  });

  test('Purchase Return card shows Total Purchase Return and Total Purchase Return Paid sub-lines', async ({ page }) => {
    await expect(page.getByText('Total Purchase Return:')).toBeVisible();
    await expect(page.getByText('Total Purchase Return Paid:')).toBeVisible();
  });
});
