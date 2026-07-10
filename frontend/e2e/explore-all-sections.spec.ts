/**
 * Exploratory E2E — visits every sidebar section, tries all primary actions,
 * screenshots every meaningful state. Used to surface UI bugs.
 * Runs against the LIVE dev DB. Uses only the dedicated E2E test user so
 * no existing user data is touched.
 */
import { test, expect, Page } from '@playwright/test';
import { ensureTestUser, loginViaAPI } from './helpers/auth';

// ── Setup ────────────────────────────────────────────────────────────────────

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaAPI(page);
});

// ── Helpers ──────────────────────────────────────────────────────────────────

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-screenshots/${name}.png`, fullPage: true });
}

async function openAddModal(page: Page): Promise<boolean> {
  const addBtn = page.getByRole('button', {
    name: /add|new|create/i,
  }).first();
  if (await addBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await addBtn.click();
    await page.waitForTimeout(600);
    return true;
  }
  return false;
}

async function dismissModal(page: Page) {
  const cancel = page.getByRole('button', { name: /cancel|close|dismiss/i }).first();
  if (await cancel.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await cancel.click();
    await page.waitForTimeout(300);
  }
}

// ── Dashboard ────────────────────────────────────────────────────────────────

test('dashboard – loads KPI cards', async ({ page }) => {
  await page.goto('/dashboard');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '01-dashboard');
  // Dashboard renders the greeting banner and named metric sections
  await expect(page.getByText("Today's Revenue")).toBeVisible();
  // Look for well-known dashboard sections
  const knownSections = ['Cash Health', 'FX Exposure', 'Profit Margin', 'Order Activity'];
  let found = 0;
  for (const s of knownSections) {
    if (await page.getByText(s).first().isVisible({ timeout: 2_000 }).catch(() => false)) found++;
  }
  expect(found).toBeGreaterThan(1);
});

// ── Sales ─────────────────────────────────────────────────────────────────────

test('sales – loads list and opens create modal', async ({ page }) => {
  await page.goto('/sales');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '02-sales-list');

  const opened = await openAddModal(page);
  await shot(page, '02-sales-add-modal');
  if (opened) {
    // The sales redesign uses a tab-based form instead of a modal dialog
    // Accept either: a dialog OR the add-sale form card becoming visible
    const dialog = page.locator('[role="dialog"]').first();
    const addSaleForm = page.locator('[data-testid="add-sale-form"], #add-sale-form, .add-sale-card').first();
    const dialogVisible = await dialog.isVisible({ timeout: 3_000 }).catch(() => false);
    const formVisible = await addSaleForm.isVisible({ timeout: 3_000 }).catch(() => false);
    // At minimum the page should have a submit button visible somewhere
    const submitBtn = page.getByRole('button', { name: /save|create|add|record/i }).first();
    const submitVisible = await submitBtn.isVisible({ timeout: 3_000 }).catch(() => false);
    expect(dialogVisible || formVisible || submitVisible).toBe(true);
    await dismissModal(page);
  }
});

// ── Products ──────────────────────────────────────────────────────────────────

test('products – loads list and add-product tab has submit button', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '03-products-list');

  // Products uses an inline tab form — click "New Product" button which activates the Add tab
  const newProductBtn = page.getByRole('button', { name: /new product/i });
  if (await newProductBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await newProductBtn.click();
  } else {
    // Try tab directly
    await page.getByRole('tab', { name: /add product/i }).click();
  }
  await page.waitForTimeout(500);
  await shot(page, '03-products-add-tab');

  // The inline form has a "Create Product" button — scroll to it if needed
  const createBtn = page.getByRole('button', { name: /create product/i });
  await createBtn.scrollIntoViewIfNeeded();
  await expect(createBtn).toBeVisible({ timeout: 5_000 });
});

// ── Inventory ─────────────────────────────────────────────────────────────────

test('inventory – loads list, opens adjust stock modal', async ({ page }) => {
  await page.goto('/inventory');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '04-inventory-list');

  // Try "Adjust" button on first row if present
  const adjustBtn = page.getByRole('button', { name: /adjust/i }).first();
  if (await adjustBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await adjustBtn.click();
    await page.waitForTimeout(600);
    await shot(page, '04-inventory-adjust-modal');
    const dialog = page.locator('[role="dialog"]').first();
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    const submitBtn = dialog.getByRole('button', {
      name: /save|adjust|confirm/i,
    }).first();
    expect(await submitBtn.isVisible({ timeout: 3_000 })).toBe(true);
    await dismissModal(page);
  }
});

// ── Stock Counts ──────────────────────────────────────────────────────────────

test('stock-counts – loads list and opens new count modal', async ({ page }) => {
  await page.goto('/stock-counts');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '05-stock-counts-list');

  const opened = await openAddModal(page);
  await shot(page, '05-stock-counts-add-modal');
  if (opened) {
    const dialog = page.locator('[role="dialog"]').first();
    const isOpen = await dialog.isVisible({ timeout: 4_000 }).catch(() => false);
    if (isOpen) {
      const submitBtn = dialog.getByRole('button', {
        name: /save|create|add|start/i,
      }).first();
      expect(await submitBtn.isVisible({ timeout: 3_000 })).toBe(true);
      await dismissModal(page);
    }
  }
});

// ── Orders ────────────────────────────────────────────────────────────────────

test('orders – loads list and opens create modal', async ({ page }) => {
  await page.goto('/orders');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '06-orders-list');

  const opened = await openAddModal(page);
  await shot(page, '06-orders-add-modal');
  if (opened) {
    const dialog = page.locator('[role="dialog"]').first();
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    const submitBtn = dialog.getByRole('button', {
      name: /save|create|add/i,
    }).first();
    expect(await submitBtn.isVisible({ timeout: 3_000 })).toBe(true);
    await dismissModal(page);
  }
});

// ── Suppliers ─────────────────────────────────────────────────────────────────

test('suppliers – loads list and opens create modal', async ({ page }) => {
  await page.goto('/suppliers');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '07-suppliers-list');

  const opened = await openAddModal(page);
  await shot(page, '07-suppliers-add-modal');
  if (opened) {
    const dialog = page.locator('[role="dialog"]').first();
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    const submitBtn = dialog.getByRole('button', {
      name: /save|create|add/i,
    }).first();
    expect(await submitBtn.isVisible({ timeout: 3_000 })).toBe(true);
    await dismissModal(page);
  }
});

// ── Pricing ───────────────────────────────────────────────────────────────────

test('pricing – loads page', async ({ page }) => {
  await page.goto('/pricing');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '08-pricing');
  // Should show content (not a 404 page) — check heading rather than body text
  // because product names can contain "404" as part of a timestamp-based ID.
  await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({ timeout: 10_000 });
});

// ── FX Rates ──────────────────────────────────────────────────────────────────

test('fx – loads rates and opens add modal', async ({ page }) => {
  await page.goto('/fx');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '09-fx-list');

  const opened = await openAddModal(page);
  await shot(page, '09-fx-add-modal');
  if (opened) {
    const dialog = page.locator('[role="dialog"]').first();
    const isOpen = await dialog.isVisible({ timeout: 4_000 }).catch(() => false);
    if (isOpen) {
      const submitBtn = dialog.getByRole('button', {
        name: /save|create|add|set/i,
      }).first();
      expect(await submitBtn.isVisible({ timeout: 3_000 })).toBe(true);
      await dismissModal(page);
    }
  }
});

// ── Cashflow ──────────────────────────────────────────────────────────────────

test('cashflow – loads charts/summary', async ({ page }) => {
  await page.goto('/cashflow');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '10-cashflow');
  await expect(page.locator('body')).not.toContainText('404');
  await expect(page.locator('body')).not.toContainText('Cannot read');
});

// ── AI Insights ───────────────────────────────────────────────────────────────

test('recommendations – loads AI insights page', async ({ page }) => {
  await page.goto('/recommendations');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '11-recommendations');
  await expect(page.locator('body')).not.toContainText('404');
});

// ── Reports ───────────────────────────────────────────────────────────────────

test('reports – loads reports page', async ({ page }) => {
  await page.goto('/reports');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '12-reports');
  await expect(page.locator('body')).not.toContainText('404');
});

// ── Invoice Schemes ───────────────────────────────────────────────────────────

test('invoice-schemes – loads list and opens create modal', async ({ page }) => {
  await page.goto('/settings/invoice-schemes');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '13-invoice-schemes-list');

  const opened = await openAddModal(page);
  await shot(page, '13-invoice-schemes-add-modal');
  if (opened) {
    const dialog = page.locator('[role="dialog"]').first();
    const isOpen = await dialog.isVisible({ timeout: 4_000 }).catch(() => false);
    if (isOpen) {
      const submitBtn = dialog.getByRole('button', {
        name: /save|create|add/i,
      }).first();
      expect(await submitBtn.isVisible({ timeout: 3_000 })).toBe(true);
      await dismissModal(page);
    }
  }
});

// ── Locations ─────────────────────────────────────────────────────────────────

test('locations – loads list, opens modal, modal has submit button', async ({ page }) => {
  await page.goto('/settings/locations');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '14-locations-list');

  // The known bug: modal was opened but had no submit button
  const addBtn = page.getByRole('button', { name: 'Add Location' });
  await expect(addBtn).toBeVisible({ timeout: 5_000 });
  await addBtn.click();

  const dialog = page.locator('[role="dialog"]').filter({ hasText: /add location/i });
  await expect(dialog).toBeVisible({ timeout: 5_000 });
  await shot(page, '14-locations-add-modal');

  // This is the previously-reported bug — ensure submit button IS present
  const submitBtn = dialog.getByRole('button', { name: /add location/i });
  await expect(submitBtn).toBeVisible({ timeout: 3_000 });
  await dismissModal(page);
});

// ── Settings ──────────────────────────────────────────────────────────────────

test('settings – loads page with API key section', async ({ page }) => {
  await page.goto('/settings');
  await page.waitForLoadState('domcontentloaded');
  await shot(page, '15-settings');
  await expect(page.locator('body')).not.toContainText('404');
  // Should have an API key or profile section
  const hasContent = await page.locator('input, [class*="form"], [class*="card"]').count();
  expect(hasContent).toBeGreaterThan(0);
});
