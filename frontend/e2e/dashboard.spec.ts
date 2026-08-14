import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';
import { ensureProduct, createOrder, deleteOrder, createLoan, addStock, createSale } from './helpers/data';

const API = 'http://localhost:8000/api/v1';

// ---------------------------------------------------------------------------
// Dashboard E2E Tests
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.waitForLoadState('domcontentloaded');
  // Wait for the page to settle past the loading skeleton
  await page.locator('[data-testid="dashboard-filter-bar"]')
    .waitFor({ timeout: 20000 }).catch(() => {});
});

// ---------------------------------------------------------------------------
// Tasks 148–151: unified layout
// ---------------------------------------------------------------------------

test.describe('Dashboard unified layout — Tasks 148-151', () => {
  test('filter bar appears before hero cards in DOM order (Task 148)', async ({ page }) => {
    const filterBar = page.locator('[data-testid="dashboard-filter-bar"]');
    const heroCard  = page.locator('[data-testid="hero-revenue-card"]');
    await expect(filterBar).toBeVisible();
    await expect(heroCard).toBeVisible();
    const filterBox = await filterBar.boundingBox();
    const heroBox   = await heroCard.boundingBox();
    expect(filterBox!.y).toBeLessThan(heroBox!.y);
  });

  test('hero row shows Net Profit not Profit Margin (%) (Task 149)', async ({ page }) => {
    await expect(page.getByText('Net Profit').first()).toBeVisible();
    await expect(page.getByText('Profit Margin (%)')).toHaveCount(0);
  });

  test('Total Sales KPI card not present anywhere on page (Task 149)', async ({ page }) => {
    // Sections are collapsed — any stray "Total Sales" text means the card leaked back in
    await expect(page.getByText('Total Sales')).toHaveCount(0);
  });

  test('Currency & Import Risks card shows both sub-sections (Task 150)', async ({ page }) => {
    // Card lives inside the Pulse Metrics accordion — open it first
    await page.getByText('Pulse Metrics').click();
    await expect(page.getByText('Currency & Import Risks').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('Open Order Exposure').first()).toBeVisible();
    await expect(page.getByText('Total Obligations').first()).toBeVisible();
  });

  test('Shipping Costs card has no threshold table (Task 151)', async ({ page }) => {
    // Card lives inside the Stock & Purchase Metrics accordion — open it first
    await page.getByText('Stock & Purchase Metrics').click();
    await expect(page.getByText('Shipping Costs').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('90-day rolling average').first()).toBeVisible();
    // "Caution" row was removed from the threshold table
    await expect(page.getByText('Caution')).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// Accordion structure
// ---------------------------------------------------------------------------

test.describe('KPI accordion structure', () => {
  test('all five accordion section labels are visible on load', async ({ page }) => {
    await expect(page.getByText('Money Out').first()).toBeVisible();
    await expect(page.getByText('Returns').first()).toBeVisible();
    await expect(page.getByText('Stock & Purchase Metrics').first()).toBeVisible();
    await expect(page.getByText('Pulse Metrics').first()).toBeVisible();
    await expect(page.getByText('AI Smart Suggestions').first()).toBeVisible();
  });

  test('Money Out section expands and reveals KPI cards', async ({ page }) => {
    await expect(page.getByText('Total Purchased')).not.toBeVisible();
    await page.getByText('Money Out').click();
    await expect(page.getByText('Total Purchased').first()).toBeVisible();
    await expect(page.getByText('Amount Owed').first()).toBeVisible();
    await expect(page.getByText('Monthly Expenses').first()).toBeVisible();
  });

  test('Returns section expands and reveals KPI cards', async ({ page }) => {
    await expect(page.getByText('Customer Returns')).not.toBeVisible();
    await page.getByText('Returns').click();
    await expect(page.getByText('Customer Returns').first()).toBeVisible();
    await expect(page.getByText('Supplier Refunds').first()).toBeVisible();
  });

  test('Stock & Purchase Metrics expands and reveals cards', async ({ page }) => {
    await expect(page.getByText('Stock Levels')).not.toBeVisible();
    await page.getByText('Stock & Purchase Metrics').click();
    await expect(page.getByText('Stock Levels').first()).toBeVisible();
    await expect(page.getByText('Order Activity').first()).toBeVisible();
    await expect(page.getByText('Shipping Costs').first()).toBeVisible();
  });

  test('Pulse Metrics expands and reveals cards', async ({ page }) => {
    await expect(page.getByText('Margin vs Target')).not.toBeVisible();
    await page.getByText('Pulse Metrics').click();
    await expect(page.getByText('Margin vs Target').first()).toBeVisible();
    await expect(page.getByText('Cash Health').first()).toBeVisible();
    await expect(page.getByText('Currency & Import Risks').first()).toBeVisible({ timeout: 15_000 });
  });

  test('AI Smart Suggestions expands and reveals card', async ({ page }) => {
    await expect(page.getByText('Smart Suggestions')).not.toBeVisible();
    await page.getByText('AI Smart Suggestions').click();
    await expect(page.getByText('Smart Suggestions').first()).toBeVisible();
  });

  test('accordion collapses again on second click', async ({ page }) => {
    // Open Money Out then close it
    await page.getByText('Money Out').click();
    await expect(page.getByText('Total Purchased').first()).toBeVisible();
    await page.getByText('Money Out').click();
    await expect(page.getByText('Total Purchased')).not.toBeVisible();
  });

  test('accordion buttons have aria-expanded attribute', async ({ page }) => {
    const moneyOutBtn = page.getByRole('button', { name: /money out/i });
    await expect(moneyOutBtn).toHaveAttribute('aria-expanded', 'false');
    await moneyOutBtn.click();
    await expect(moneyOutBtn).toHaveAttribute('aria-expanded', 'true');
  });
});

// ---------------------------------------------------------------------------
// Widget cards — each group opens its parent accordion first
// ---------------------------------------------------------------------------

test.describe('Stock & Purchase Metrics cards', () => {
  test.beforeEach(async ({ page }) => {
    await page.getByText('Stock & Purchase Metrics').click();
  });

  test('displays the Stock Levels card', async ({ page }) => {
    await expect(page.getByText('Stock Levels').first()).toBeVisible();
  });

  test('displays the Order Activity card', async ({ page }) => {
    await expect(page.getByText('Order Activity').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('In Progress').first()).toBeVisible({ timeout: 10_000 });
  });

  test('displays the Shipping Costs card with rolling average', async ({ page }) => {
    await expect(page.getByText('Shipping Costs').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('90-day rolling average').first()).toBeVisible();
  });

  test('Shipping Costs shows a numeric percentage value', async ({ page }) => {
    const pctElement = page.locator('p.text-4xl.font-bold').filter({ hasText: /%/ });
    await expect(pctElement).toBeVisible();
    await expect(pctElement).toContainText(/\d+\.\d%/);
  });
});

test.describe('Pulse Metrics cards', () => {
  test.beforeEach(async ({ page }) => {
    await page.getByText('Pulse Metrics').click();
  });

  test('displays the Cash Health card', async ({ page }) => {
    await expect(page.getByText('Cash Health').first()).toBeVisible();
    await expect(page.getByText('Cash Runway').first()).toBeVisible();
    await expect(page.getByText('Profit Score (DSCR)').first()).toBeVisible();
  });

  test('displays the Margin vs Target card', async ({ page }) => {
    await expect(page.getByText('Margin vs Target').first()).toBeVisible();
    await expect(page.getByText('Target:').first()).toBeVisible();
  });

  test('displays the Currency & Import Risks card', async ({ page }) => {
    await expect(page.getByText('Currency & Import Risks').first()).toBeVisible({ timeout: 15_000 });
    const hasExposure = await page.getByText('No FX exposure tracked yet').isVisible().catch(() => false);
    const hasRows = await page.locator('.rounded-xl.border.border-gray-100').first().isVisible().catch(() => false);
    expect(hasExposure || hasRows).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Task 189 — Cash Health card had the same 999-sentinel leak and
// yellow/amber DSCR-color bug as the Cashflow page (fixed there in task 187).
// ---------------------------------------------------------------------------

test.describe('Cash Health card — 999 sentinel and risk-color parity (Task 189)', () => {
  test.beforeEach(async ({ page }) => {
    await page.getByText('Pulse Metrics').click();
    await expect(page.getByText('Cash Health').first()).toBeVisible();
  });

  // These two only assert the raw sentinel never leaks — not that the
  // account is currently debt/burn-free — because other spec files sharing
  // this CI run's DB (e.g. cashflow.spec.ts's loan-creating tests) may have
  // already put the shared test business into a finite-DSCR/finite-runway
  // state by the time this file runs. Mirrors the same robust pattern
  // cashflow.spec.ts uses for its task 187 sentinel tests.

  test('Cash Runway never shows the raw 999 sentinel', async ({ page }) => {
    await expect(page.getByText(/999\.0/, { exact: false })).not.toBeVisible();
  });

  test('Profit Score (DSCR) never shows the raw 999 sentinel', async ({ page }) => {
    await expect(page.getByText('999.0', { exact: true })).not.toBeVisible();
  });

  test('risk badge shows Caution, not At Risk, for a medium-risk (amber) DSCR', async ({ page }) => {
    // Size a loan so DSCR lands in the 1.0-1.49 "amber" band: the backend
    // color-codes that band as amber, and the old dashboard.service.ts
    // mapping (`=== 'yellow'`) never matched it, silently inflating a
    // medium-risk account to the HIGH/"At Risk" badge.
    //
    // Seed a large, deterministic sale first so net_operating_income is
    // guaranteed positive regardless of what other spec files sharing this
    // CI run's DB have already done.
    const product = await ensureProduct('E2E Amber DSCR Product');
    await addStock(product.id, 100);
    await createSale(product.id, { quantity: 10, unitPrice: '300000.00' });

    const token = await getAPIToken();
    const ctx = await request.newContext();
    const dscrResp = await ctx.get(`${API}/cashflow/dscr`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const { net_operating_income } = await dscrResp.json();
    await ctx.dispose();
    const noi = parseFloat(net_operating_income);
    expect(noi).toBeGreaterThan(0);
    const monthlyPayment = (noi / 1.25).toFixed(2);

    await createLoan('E2E Amber DSCR Bank', '1000000.00', monthlyPayment);
    await page.reload();
    await page.waitForLoadState('domcontentloaded');
    await page.getByText('Pulse Metrics').click();
    await expect(page.getByText('Cash Health').first()).toBeVisible();

    await expect(page.getByText('Caution', { exact: true })).toBeVisible();
    await expect(page.getByText('At Risk', { exact: true })).not.toBeVisible();
  });
});

test.describe('AI Smart Suggestions card', () => {
  test.beforeEach(async ({ page }) => {
    await page.getByText('AI Smart Suggestions').click();
  });

  test('displays the Smart Suggestions card', async ({ page }) => {
    await expect(page.getByText('Smart Suggestions').first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Currency & Import Risks — global exposure data (Task 16)
// ---------------------------------------------------------------------------

test.describe('Currency & Import Risks — global exposure (Task 16)', () => {
  let usdOrderId: string;

  test.beforeAll(async () => {
    const product = await ensureProduct('E2E Global Exposure Product');
    const order = await createOrder(product.id, { currency: 'USD', quantity: 5, unitCost: '200.00' });
    usdOrderId = order.id;
  });

  test.afterAll(async () => {
    if (usdOrderId) await deleteOrder(usdOrderId);
  });

  test.beforeEach(async ({ page }) => {
    await page.getByText('Pulse Metrics').click();
  });

  test('renders total obligations when data is available', async ({ page }) => {
    await expect(page.getByText('Currency & Import Risks').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('EUR Loan Balance').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('USD Order Obligations').first()).toBeVisible();
    await expect(page.getByText('Total Amount Owed (₦)').first()).toBeVisible();
    await expect(page.getByText('Risk Level:').first()).toBeVisible();
  });

  test('shows numeric total exposure value', async ({ page }) => {
    const totalEl = page.locator('p.text-2xl.font-bold.text-indigo-700').first();
    await expect(totalEl).toBeVisible();
    await expect(totalEl).toContainText(/₦[\d,]+/);
  });

  test('shows debt-to-trade ratio as a decimal', async ({ page }) => {
    const ratioEl = page.locator('span.text-xs.font-bold').filter({ hasText: /\d+\.\d{2}/ }).first();
    await expect(ratioEl).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Recent Sales — mobile stacked cards vs desktop table (Task 144)
// ---------------------------------------------------------------------------

test.describe('Recent Sales — mobile stacked cards vs desktop table (Task 144)', () => {
  test('shows stacked card list on mobile (375px) and hides the table', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    const table = page.locator('table').first();
    await expect(table).toBeHidden();
    const mobileList = page.locator('div.block.sm\\:hidden');
    await expect(mobileList).toBeVisible();
  });

  test('shows table on desktop (768px) and hides the card list', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    const table = page.locator('table').first();
    await expect(table).toBeVisible();
    const mobileList = page.locator('div.block.sm\\:hidden');
    await expect(mobileList).toBeHidden();
  });

  test('mobile card rows meet 44px tap target', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    const mobileList = page.locator('div.block.sm\\:hidden');
    await expect(mobileList).toBeAttached();
    const firstRow = mobileList.locator('div.min-h-\\[44px\\]').first();
    const hasRows = await firstRow.isVisible().catch(() => false);
    if (hasRows) {
      const box = await firstRow.boundingBox();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
  });
});
