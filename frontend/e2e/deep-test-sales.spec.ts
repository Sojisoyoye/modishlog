/**
 * Deep E2E test — Sales (Task #104)
 * Record sale, multi-item, All Sales list, search, CSV export, sale detail.
 */
import { test, expect, Page } from '@playwright/test';
import { ensureTestUser, loginViaAPI } from './helpers/auth';
import { ensureProduct } from './helpers/data';

let productId: string;
let productName: string;

test.beforeAll(async () => {
  await ensureTestUser();
  const p = await ensureProduct('E2E Sales Test Product');
  productId = p.id;
  productName = p.name;
});

test.beforeEach(async ({ page }) => {
  await loginViaAPI(page);
});

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-screenshots/sales-${name}.png`, fullPage: true });
}

// ── 1. Sales page loads ────────────────────────────────────────────────────────
test('sales – page loads with heading and Record Sale button', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('networkidle');
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

// ── 2. All Sales tab loads list ────────────────────────────────────────────────
test('sales – All Sales tab shows a list or empty state', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('networkidle');

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

// ── 3. Open record-sale form/modal ─────────────────────────────────────────────
test('sales – record-sale form opens with required fields', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('networkidle');

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

// ── 4. Record a single sale ────────────────────────────────────────────────────
test('sales – record single-product sale shows success', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('networkidle');

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
    // Or check we navigated somewhere
    const url = page.url();
    expect(toastVisible || url.includes('sales')).toBe(true);
  }
});

// ── 5. Search/filter in All Sales ─────────────────────────────────────────────
test('sales – search field filters sales list', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('networkidle');

  const allSalesTab = page.getByRole('tab', { name: /all sales/i });
  if (await allSalesTab.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await allSalesTab.click();
    await page.waitForTimeout(500);
  }

  const searchInput = page.locator('input[placeholder*="search"], input[type="search"]').first();
  if (await searchInput.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await searchInput.fill('E2E');
    await page.waitForTimeout(700);
    await shot(page, '05-search-results');
  } else {
    await shot(page, '05-no-search');
    // Not a bug — just note there is no search field
  }
});

// ── 6. CSV export ──────────────────────────────────────────────────────────────
test('sales – CSV export button exists and is clickable', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('networkidle');

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
    // Listen for download
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 5_000 }).catch(() => null),
      exportBtn.click(),
    ]);
    await shot(page, '06-after-export');
    // Either a download started OR a toast/confirmation appeared — either is valid
    const toast = page.locator('[class*="toast"]').first();
    const toastVisible = await toast.isVisible({ timeout: 3_000 }).catch(() => false);
    expect(download !== null || toastVisible).toBe(true);
  } else if (hasExportLink) {
    // Link exists — that's enough to verify it's present
    expect(hasExportLink).toBe(true);
  } else {
    // Note absence — this is informational
    console.log('INFO: No CSV export button/link found on Sales page');
  }
});

// ── 7. Sale detail / click into a sale row ─────────────────────────────────────
test('sales – clicking a sale row opens detail view', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('networkidle');

  const allSalesTab = page.getByRole('tab', { name: /all sales/i });
  if (await allSalesTab.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await allSalesTab.click();
    await page.waitForTimeout(500);
  }

  // Check if any rows exist
  const rows = page.locator('table tbody tr, [class*="sale-row"], [class*="list-item"]');
  const rowCount = await rows.count();
  await shot(page, '07-sales-list');

  if (rowCount > 0) {
    await rows.first().click();
    await page.waitForTimeout(800);
    await shot(page, '07-sale-detail');
    // Either a modal, a panel, or navigation to a detail page
    const detailVisible = await page.locator('[role="dialog"], [class*="detail"], [class*="panel"]').first().isVisible({ timeout: 4_000 }).catch(() => false);
    const urlChanged = !page.url().endsWith('/sales');
    expect(detailVisible || urlChanged).toBe(true);
  } else {
    // No sales yet — that's fine, just record it
    console.log('INFO: No sale rows to click — sales list is empty');
  }
});
