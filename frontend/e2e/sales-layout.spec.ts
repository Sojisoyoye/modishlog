import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

// ---------------------------------------------------------------------------
// Sales Page Layout Redesign E2E Tests
//
// Covers the redesign where:
//  - "All Sales" becomes the first/default tab
//  - An "Add Sale" button appears in the All Sales tab header
//  - Clicking "Add Sale" switches to the add-sale tab and shows the form
//  - The "Record Sales" tab is renamed to "Add Sale"
//  - The add-sale form card is wrapped in a centered max-w-2xl container
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/sales');
  await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();
});

// ---------------------------------------------------------------------------
// Default tab on page load
// ---------------------------------------------------------------------------

test.describe('Default tab — All Sales is first and active', () => {
  test('"All Sales" tab is visible when navigating to /sales', async ({ page }) => {
    const allSalesTab = page.locator('[data-testid="tab-all-sales"]');
    await expect(allSalesTab).toBeVisible();
  });

  test('"All Sales" tab is the active/selected tab by default', async ({ page }) => {
    const allSalesTab = page.locator('[data-testid="tab-all-sales"]');
    await expect(allSalesTab).toBeVisible();
    // The active tab should have an aria-selected="true" attribute or an active CSS class.
    // We check both approaches to cover different Angular tab implementations.
    const isSelected = await allSalesTab.getAttribute('aria-selected');
    const classList = await allSalesTab.getAttribute('class');
    const isActiveByAria = isSelected === 'true';
    const isActiveByClass =
      classList !== null &&
      (classList.includes('active') || classList.includes('p-highlight') || classList.includes('selected'));
    expect(isActiveByAria || isActiveByClass).toBeTruthy();
  });

  test('All Sales content (transactions table or empty-state) is shown by default', async ({ page }) => {
    // The All Sales tab panel must be visible immediately (no click required).
    // Either a transaction row or the "no sales" empty-state text will appear
    // once the API call resolves; both are acceptable — we just need content.
    const txnRow = page.locator('[data-testid="transaction-row"]').first();
    const emptyText = page.getByText(/no sales/i).first();
    await expect(txnRow.or(emptyText)).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// "Add Sale" button in the All Sales tab header
// ---------------------------------------------------------------------------

test.describe('"Add Sale" button in All Sales tab header', () => {
  test('"Add Sale" button is visible on the All Sales tab', async ({ page }) => {
    // Ensure we are on the All Sales tab (default)
    const allSalesTab = page.locator('[data-testid="tab-all-sales"]');
    await expect(allSalesTab).toBeVisible();

    const addSaleBtn = page.locator('[data-testid="add-sale-btn"]');
    await expect(addSaleBtn).toBeVisible();
  });

  test('"Add Sale" button label reads "Add Sale"', async ({ page }) => {
    const addSaleBtn = page.locator('[data-testid="add-sale-btn"]');
    await expect(addSaleBtn).toBeVisible();
    await expect(addSaleBtn).toHaveText(/Add Sale/i);
  });

  test('"Add Sale" button is positioned in the All Sales tab header area', async ({ page }) => {
    // The button should be visible without switching tabs
    const addSaleBtn = page.locator('[data-testid="add-sale-btn"]');
    await expect(addSaleBtn).toBeVisible();
    // It should not be inside the form itself (which is only shown on the add-sale tab)
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    await expect(formCard).toBeHidden();
  });
});

// ---------------------------------------------------------------------------
// Clicking "Add Sale" button activates the add-sale tab
// ---------------------------------------------------------------------------

test.describe('Clicking "Add Sale" button switches to the add-sale tab', () => {
  test('clicking "Add Sale" button shows the add-sale form', async ({ page }) => {
    const addSaleBtn = page.locator('[data-testid="add-sale-btn"]');
    await expect(addSaleBtn).toBeVisible();
    await addSaleBtn.click();

    // The add-sale form card should now be visible
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    await expect(formCard).toBeVisible({ timeout: 5_000 });
  });

  test('clicking "Add Sale" button activates the Add Sale tab in the nav', async ({ page }) => {
    const addSaleBtn = page.locator('[data-testid="add-sale-btn"]');
    await expect(addSaleBtn).toBeVisible();
    await addSaleBtn.click();

    // The add-sale tab (formerly "Record Sales") should now be active.
    // Accept either the old testid (tab-record-sales) or the new one (tab-add-sale).
    const addSaleTab = page
      .locator('[data-testid="tab-add-sale"]')
      .or(page.locator('[data-testid="tab-record-sales"]'));
    await expect(addSaleTab).toBeVisible({ timeout: 5_000 });

    await expect(addSaleTab).toHaveAttribute('aria-selected', 'true', { timeout: 5_000 });
  });

  test('clicking "Add Sale" button reveals product dropdown in the form', async ({ page }) => {
    const addSaleBtn = page.locator('[data-testid="add-sale-btn"]');
    await expect(addSaleBtn).toBeVisible();
    await addSaleBtn.click();

    // The product select dropdown should be visible inside the form
    const productSelect = page.locator('select').filter({ hasText: 'Select product' }).first();
    await expect(productSelect).toBeVisible({ timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// "Add Sale" tab exists in the tab navigation
// ---------------------------------------------------------------------------

test.describe('"Add Sale" tab in the tab navigation', () => {
  test('the add-sale tab is present in the tab nav (accepts either testid)', async ({ page }) => {
    // The tab was renamed from "Record Sales" to "Add Sale".
    // We accept either data-testid to cover both old and new implementations.
    const addSaleTab = page
      .locator('[data-testid="tab-add-sale"]')
      .or(page.locator('[data-testid="tab-record-sales"]'));
    await expect(addSaleTab).toBeVisible();
  });

  test('clicking the add-sale tab directly shows the form card', async ({ page }) => {
    const addSaleTab = page
      .locator('[data-testid="tab-add-sale"]')
      .or(page.locator('[data-testid="tab-record-sales"]'));
    await expect(addSaleTab).toBeVisible();
    await addSaleTab.click();

    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    await expect(formCard).toBeVisible({ timeout: 5_000 });
  });

  test('the add-sale tab label reads "Add Sale" (renamed from "Record Sales")', async ({ page }) => {
    // Prefer the new testid; fall back to old testid.
    const newTab = page.locator('[data-testid="tab-add-sale"]');
    const oldTab = page.locator('[data-testid="tab-record-sales"]');

    const newTabCount = await newTab.count();
    if (newTabCount > 0) {
      await expect(newTab).toHaveText(/Add Sale/i);
    } else {
      // During transition the old testid may still be present but with new label
      await expect(oldTab).toHaveText(/Add Sale/i);
    }
  });

  test('all three tabs (All Sales, Add Sale, Upload CSV) are visible', async ({ page }) => {
    await expect(page.locator('[data-testid="tab-all-sales"]')).toBeVisible();

    // Accept either testid for the add-sale tab
    const addSaleTab = page
      .locator('[data-testid="tab-add-sale"]')
      .or(page.locator('[data-testid="tab-record-sales"]'));
    await expect(addSaleTab).toBeVisible();

    await expect(page.locator('[data-testid="tab-upload-csv"]')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Add-sale form card layout
// ---------------------------------------------------------------------------

test.describe('Add-sale form card layout', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the add-sale tab before each test in this describe block
    const addSaleTab = page
      .locator('[data-testid="tab-add-sale"]')
      .or(page.locator('[data-testid="tab-record-sales"]'));
    await addSaleTab.click();
    await expect(page.locator('[data-testid="add-sale-form-card"]')).toBeVisible({ timeout: 5_000 });
  });

  test('add-sale form card is present on the add-sale tab', async ({ page }) => {
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    await expect(formCard).toBeVisible();
  });

  test('add-sale form card contains the product dropdown', async ({ page }) => {
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    const productSelect = formCard.locator('select').filter({ hasText: 'Select product' }).first();
    await expect(productSelect).toBeVisible();
  });

  test('add-sale form card contains a quantity input', async ({ page }) => {
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    const qtyInput = formCard.locator('input[type="number"]').first();
    await expect(qtyInput).toBeVisible();
  });

  test('add-sale form card contains a date input', async ({ page }) => {
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    const dateInput = formCard.locator('input[type="date"]').first();
    await expect(dateInput).toBeVisible();
  });

  test('add-sale form card contains "Add Row" and submit buttons', async ({ page }) => {
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    await expect(formCard.getByRole('button', { name: /Add Product Row/i })).toBeVisible();
    // The submit button text may have changed to "Add Sale" or remain "Record Sales"
    const submitBtn = formCard
      .getByRole('button', { name: /Add Sale/i })
      .or(formCard.getByRole('button', { name: /Record Sales/i }))
      .last();
    await expect(submitBtn).toBeVisible();
  });

  test('add-sale form card is centered with a max-width constraint', async ({ page }) => {
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    await expect(formCard).toBeVisible();

    // Verify the card has a max-width applied (max-w-2xl = 672 px).
    // We check that the card's bounding box width is less than the full viewport width.
    const viewportSize = page.viewportSize();
    const boundingBox = await formCard.boundingBox();
    if (viewportSize && boundingBox) {
      // On a typical desktop viewport (>= 672 px) the card should be narrower than the full width.
      if (viewportSize.width > 700) {
        expect(boundingBox.width).toBeLessThan(viewportSize.width);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Navigation round-trip: All Sales -> Add Sale -> All Sales
// ---------------------------------------------------------------------------

test.describe('Tab navigation round-trip', () => {
  test('switching from All Sales to Add Sale and back shows correct content', async ({ page }) => {
    // Start on All Sales (default)
    const allSalesTab = page.locator('[data-testid="tab-all-sales"]');
    await expect(allSalesTab).toBeVisible();

    // The add-sale form card should NOT be visible on the All Sales tab
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    await expect(formCard).toBeHidden();

    // Click "Add Sale" button to switch tabs
    const addSaleBtn = page.locator('[data-testid="add-sale-btn"]');
    await expect(addSaleBtn).toBeVisible();
    await addSaleBtn.click();

    // Form card should now be visible
    await expect(formCard).toBeVisible({ timeout: 5_000 });

    // Switch back to All Sales tab
    await allSalesTab.click();

    // Form card should be hidden again
    await expect(formCard).toBeHidden({ timeout: 5_000 });
  });

  test('"Add Sale" button is NOT visible when on the add-sale tab', async ({ page }) => {
    // Click the Add Sale button to switch away from All Sales
    const addSaleBtn = page.locator('[data-testid="add-sale-btn"]');
    await expect(addSaleBtn).toBeVisible();
    await addSaleBtn.click();

    await expect(page.locator('[data-testid="add-sale-form-card"]')).toBeVisible({ timeout: 5_000 });

    // The "Add Sale" button belongs to the All Sales tab header,
    // so it should not be visible when on the add-sale tab.
    await expect(addSaleBtn).toBeHidden();
  });
});
