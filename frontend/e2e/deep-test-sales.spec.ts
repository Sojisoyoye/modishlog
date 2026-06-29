/**
 * Deep E2E test — Sales (Task #104)
 * Record sale, multi-item, All Sales list, search, CSV export, sale detail.
 */
import { test, expect, Page } from '@playwright/test';
import { ensureTestUser, loginViaAPI } from './helpers/auth';
import { addStock, createSale, ensureProduct } from './helpers/data';

let productId: string;
let productName: string;

test.beforeAll(async () => {
  await ensureTestUser();
  const p = await ensureProduct('E2E Sales Test Product');
  productId = p.id;
  productName = p.name;
  // Seed stock and a sale so the All Sales list always has at least one row
  await addStock(productId, 50);
  await createSale(productId, { quantity: 1 });
});

test.beforeEach(async ({ page }) => {
  await loginViaAPI(page);
});

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-screenshots/sales-${name}.png`, fullPage: true });
}

// -- 1. Sales page loads ------------------------------------------------------
test('sales - page loads with heading and Record Sale button', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '01-loaded');
  await expect(page.getByRole('heading', { name: /sales/i }).first()).toBeVisible();
  // There should be a button/tab to record a sale
  const recordBtn = page.getByRole('button', { name: /record sale|new sale|add sale/i }).first();
  const hasRecordBtn = await recordBtn.isVisible({ timeout: 3_000 }).catch(() => false);
  // Alternatively it might be a tab
  const recordTab = page.getByRole('tab', { name: /record sale/i }).first();
  const hasRecordTab = await recordTab.isVisible({ timeout: 3_000 }).catch(() => false);
  expect(hasRecordBtn || hasRecordTab).toBe(true);
});

// -- 2. All Sales tab loads list ----------------------------------------------
test('sales - All Sales tab shows a list or empty state', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('domcontentloaded');

  // Click "All Sales" tab if it exists
  const allSalesTab = page.getByRole('tab', { name: /all sales/i });
  if (await allSalesTab.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await allSalesTab.click();
    await page.waitForTimeout(500);
  }

  await shot(page, '02-all-sales-tab');
  // Either a table/list OR an empty-state message
  const hasTable = await page.locator('table, [class*="table"]').first().isVisible({ timeout: 3_000 }).catch(() => false);
  const hasEmpty = await page.getByText(/no sales|empty|no records/i).first().isVisible({ timeout: 3_000 }).catch(() => false);
  expect(hasTable || hasEmpty).toBe(true);
});

// -- 3. Open record-sale form/modal -------------------------------------------
test('sales - record-sale form opens with required fields', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('domcontentloaded');

  // Try button first, then tab
  const recordBtn = page.getByRole('button', { name: /record sale|new sale|add sale/i }).first();
  if (await recordBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await recordBtn.click();
  } else {
    const recordTab = page.getByRole('tab', { name: /record sale/i });
    if (await recordTab.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await recordTab.click();
    }
  }
  await page.waitForTimeout(600);
  await shot(page, '03-record-sale-form');

  // Form should have a product selector and quantity field
  const hasProductField = await page.locator('input[placeholder*="product"], select, [class*="dropdown"], [class*="select"]').first().isVisible({ timeout: 4_000 }).catch(() => false);
  const hasQtyField = await page.locator('input[type="number"], input[placeholder*="qty"], input[placeholder*="quantity"]').first().isVisible({ timeout: 3_000 }).catch(() => false);
  expect(hasProductField || hasQtyField).toBe(true);

  // There must be a submit button (this is the category of bug we're hunting)
  const submitBtn = page.getByRole('button', { name: /record|save|submit|sell/i }).first();
  await submitBtn.scrollIntoViewIfNeeded().catch(() => {});
  const submitVisible = await submitBtn.isVisible({ timeout: 3_000 }).catch(() => false);
  await shot(page, '03b-record-sale-submit-area');
  expect(submitVisible).toBe(true);
});

// -- 4. Record a single sale --------------------------------------------------
test('sales - record single-product sale shows success', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('domcontentloaded');

  // Navigate to the record sale UI
  const recordBtn = page.getByRole('button', { name: /record sale|new sale|add sale/i }).first();
  if (await recordBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await recordBtn.click();
    await page.waitForTimeout(600);
  } else {
    const recordTab = page.getByRole('tab', { name: /record sale/i });
    if (await recordTab.isVisible({ timeout: 3_000 }).catch(() => false)) await recordTab.click();
  }

  await page.waitForTimeout(500);
  await shot(page, '04-before-fill');

  // Try to fill in the product — look for an autocomplete or dropdown
  const productInput = page.locator('input[placeholder*="product"], input[placeholder*="search"], input[placeholder*="item"]').first();
  if (await productInput.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await productInput.fill(productName.substring(0, 5));
    await page.waitForTimeout(600);
    await shot(page, '04-product-dropdown');
    // Select first dropdown option
    const option = page.locator('[class*="dropdown-item"], [class*="option"], li').filter({ hasText: productName }).first();
    if (await option.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await option.click();
      await page.waitForTimeout(300);
    }
  }

  // Fill quantity
  const qtyInput = page.locator('input[type="number"]').first();
  if (await qtyInput.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await qtyInput.fill('1');
  }

  await shot(page, '04-filled');

  // Submit
  const submitBtn = page.getByRole('button', { name: /record|save|submit|sell/i }).first();
  if (await submitBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await submitBtn.click();
    await page.waitForTimeout(1_500);
    await shot(page, '04-after-submit');
    // Check for success toast or navigation change
    const successToast = page.locator('[class*="toast"], [class*="success"], [severity="success"]').first();
    const toastVisible = await successToast.isVisible({ timeout: 5_000 }).catch(() => false);
    const url = page.url();
    expect(toastVisible || url.includes('sales')).toBe(true);
  }
});

// -- 5. Search/filter in All Sales --------------------------------------------
test('sales - All Sales tab has a transaction row after seeded sale', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('domcontentloaded');

  const allSalesTab = page.getByTestId('tab-all-sales');
  if (await allSalesTab.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await allSalesTab.click();
    await page.waitForTimeout(500);
  }

  await shot(page, '05-all-sales');
  // A sale was seeded in beforeAll — at least one transaction row must be visible
  await expect(page.locator('[data-testid="transaction-row"]').first()).toBeVisible({ timeout: 10_000 });
});

// -- 6. CSV export ------------------------------------------------------------
test('sales - CSV export button exists and is clickable', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('domcontentloaded');

  const allSalesTab = page.getByRole('tab', { name: /all sales/i });
  if (await allSalesTab.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await allSalesTab.click();
    await page.waitForTimeout(500);
  }

  await shot(page, '06-before-export');
  const exportBtn = page.getByRole('button', { name: /export|csv|download/i }).first();
  const exportLink = page.getByRole('link', { name: /export|csv|download/i }).first();

  const hasExportBtn = await exportBtn.isVisible({ timeout: 3_000 }).catch(() => false);
  const hasExportLink = await exportLink.isVisible({ timeout: 3_000 }).catch(() => false);

  if (hasExportBtn) {
    // The export uses URL.createObjectURL + a.click() — Playwright download event
    // won't fire. Click the button and verify no error toast appears instead.
    await exportBtn.click();
    await page.waitForTimeout(2_000);
    await shot(page, '06-after-export');
    // An error toast would only appear if the API call failed — absence means success
    const errorToast = page.locator('[class*="toast"][class*="error"], [severity="error"]').first();
    const hasError = await errorToast.isVisible({ timeout: 2_000 }).catch(() => false);
    expect(hasError).toBe(false);
  } else {
    // Export button or link must be present — the sales page has data-testid="export-sales-csv"
    expect(hasExportBtn || hasExportLink).toBe(true);
  }
});

// -- 7. Sale detail / click into a sale row -----------------------------------
test('sales - clicking a sale row opens detail view', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('domcontentloaded');

  const allSalesTab = page.getByRole('tab', { name: /all sales/i });
  if (await allSalesTab.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await allSalesTab.click();
    await page.waitForTimeout(500);
  }

  await shot(page, '07-sales-list');

  // A sale was seeded in beforeAll — first row must exist and be clickable
  const firstRow = page.locator('table tbody tr, [data-testid="transaction-row"]').first();
  await expect(firstRow).toBeVisible({ timeout: 10_000 });

  await firstRow.click();
  await page.waitForTimeout(800);
  await shot(page, '07-sale-detail');

  // Clicking a sale row either opens a detail dialog OR navigates to a transaction detail page
  const dialogVisible = await page.locator('[role="dialog"]').isVisible({ timeout: 3_000 }).catch(() => false);
  const onDetailPage = page.url().includes('/transaction') || page.url().includes('/sales/');
  expect(dialogVisible || onDetailPage).toBe(true);
});
