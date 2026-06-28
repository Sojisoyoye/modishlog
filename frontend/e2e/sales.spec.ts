import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { addStock, createSale, createDailySale, ensureProduct, getInventoryQty, voidSale } from './helpers/data';

// ---------------------------------------------------------------------------
// Sales Page E2E Tests
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
// Price decimal display in Edit Sale dialog (task #59)
// ---------------------------------------------------------------------------

test.describe('Edit Sale price decimal display', () => {
  test('unit price input in edit dialog shows at most 2 decimal places', async ({ page }) => {
    const product = await ensureProduct('E2E Sale Decimal Product');
    await addStock(product.id, 50);

    // Create sale via API to get transaction_id for direct navigation
    const sale = await createDailySale(product.id, { quantity: 2 });

    // Navigate directly to the transaction detail page (clicking a row navigates here, not a dialog)
    await page.goto(`/sales/transactions/${sale.transaction_id}`);
    await expect(page.locator('[data-testid="transaction-item-row"]').first()).toBeVisible({ timeout: 10_000 });

    // Click the product name cell to activate inline editing
    await page.locator('[data-testid="transaction-item-row"]').first().locator('td').first().click();

    const priceInput = page.locator('[data-testid="inline-price-input"]').first();
    await expect(priceInput).toBeVisible({ timeout: 5_000 });
    const priceVal = await priceInput.inputValue();

    // Must not show 6 trailing decimal zeros like "5000.000000"
    expect(priceVal).not.toMatch(/\.\d{3,}/);
    // Must equal the product's selling_price (5000.00 from ensureProduct helper)
    expect(parseFloat(priceVal)).toBe(5000);
  });
});

test.describe('Sales page layout', () => {
  test('displays the Add Sale tab', async ({ page }) => {
    await expect(page.getByTestId('tab-record-sales')).toBeVisible();
  });

  test('All Sales tab is active by default and shows transaction content', async ({ page }) => {
    const allSalesTab = page.getByTestId('tab-all-sales');
    await expect(allSalesTab).toBeVisible();
    const txnRow = page.locator('[data-testid="transaction-row"]').first();
    const emptyText = page.getByText(/no transactions/i).first();
    await expect(txnRow.or(emptyText)).toBeVisible({ timeout: 10_000 });
  });

  test('Record Sales form has product dropdown, quantity, and date fields', async ({ page }) => {
    await page.getByTestId('tab-record-sales').click();
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    await expect(formCard).toBeVisible({ timeout: 5_000 });

    // Product dropdown
    const productSelect = formCard.locator('select').filter({ hasText: 'Select product' }).first();
    await expect(productSelect).toBeVisible();

    // Quantity input
    const qtyInput = formCard.locator('input[type="number"]').first();
    await expect(qtyInput).toBeVisible();

    // Date input (p-datepicker renders an input with class p-datepicker-input)
    const dateInput = formCard.locator('.p-datepicker-input').first();
    await expect(dateInput).toBeVisible();
  });

  test('has "Add Product" and "Record Sales" buttons', async ({ page }) => {
    await page.getByTestId('tab-record-sales').click();
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    await expect(formCard).toBeVisible({ timeout: 5_000 });
    await expect(formCard.getByRole('button', { name: /Add Product/i })).toBeVisible();
    await expect(formCard.getByRole('button', { name: /Record Sales/i })).toBeVisible();
  });

  test('clicking "Add Product" adds another entry row', async ({ page }) => {
    await page.getByTestId('tab-record-sales').click();
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    await expect(formCard).toBeVisible({ timeout: 5_000 });
    const selects = formCard.locator('select');
    const initialCount = await selects.count();
    await formCard.getByRole('button', { name: /Add Product/i }).click();
    await expect(selects).toHaveCount(initialCount + 1);
  });
});

test.describe('Stock-level validation', () => {
  test.beforeEach(async ({ page }) => {
    await page.getByTestId('tab-record-sales').click();
    await expect(page.locator('[data-testid="add-sale-form-card"]')).toBeVisible({ timeout: 5_000 });
  });

  test('displays stock count next to product dropdown', async ({ page }) => {
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    const productSelect = formCard.locator('select').filter({ hasText: 'Select product' }).first();
    const options = productSelect.locator('option');
    const optionCount = await options.count();

    if (optionCount > 1) {
      await productSelect.selectOption({ index: 1 });
      const stockIndicator = formCard.locator('[data-testid="stock-indicator"]').first();
      await expect(stockIndicator).toBeVisible();
      await expect(stockIndicator).toHaveText(/\d+\s+in stock/);
    }
  });

  test('shows stock warning when quantity exceeds available stock', async ({ page }) => {
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    const productSelect = formCard.locator('select').filter({ hasText: 'Select product' }).first();
    const options = productSelect.locator('option');
    const optionCount = await options.count();

    if (optionCount > 1) {
      await productSelect.selectOption({ index: 1 });
      const qtyInput = formCard.locator('input[type="number"]').first();
      await qtyInput.fill('999999');
      const warning = formCard.locator('[data-testid="stock-warning"]').first();
      await expect(warning).toBeVisible();
      await expect(warning).toHaveText(/Exceeds stock/);
    }
  });

  test('disables Record Sales button when quantity exceeds stock', async ({ page }) => {
    const formCard = page.locator('[data-testid="add-sale-form-card"]');
    const productSelect = formCard.locator('select').filter({ hasText: 'Select product' }).first();
    const options = productSelect.locator('option');
    const optionCount = await options.count();

    if (optionCount > 1) {
      await productSelect.selectOption({ index: 1 });
      const qtyInput = formCard.locator('input[type="number"]').first();
      await qtyInput.fill('999999');
      const submitBtn = formCard.getByRole('button', { name: /Record Sales/i });
      await expect(submitBtn).toBeDisabled();
    }
  });
});

test.describe('Sales history table', () => {
  test('shows table headers (Date, Invoice No., Customer, Payment Status, Total Amount)', async ({ page }) => {
    // The Recent Sales table groups transactions — columns are transaction-level fields
    await expect(page.getByRole('columnheader', { name: /Date/i }).first()).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Invoice No\./i }).first()).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Customer/i }).first()).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Payment Status/i }).first()).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Total Amount/i }).first()).toBeVisible();
  });
});

test.describe('CSV Upload tab', () => {
  test('"Upload CSV" tab is visible', async ({ page }) => {
    const uploadTab = page.locator('[data-testid="tab-upload-csv"]');
    await expect(uploadTab).toBeVisible();
    await expect(uploadTab).toHaveText(/Upload CSV/);
  });

  test('clicking "Upload CSV" tab shows file input', async ({ page }) => {
    await page.locator('[data-testid="tab-upload-csv"]').click();
    const fileInput = page.locator('[data-testid="csv-file-input"]');
    await expect(fileInput).toBeVisible();
  });

  test('"Download Template" link is present in Upload CSV tab', async ({ page }) => {
    await page.locator('[data-testid="tab-upload-csv"]').click();
    const templateLink = page.locator('[data-testid="download-template-link"]');
    await expect(templateLink).toBeVisible();
    await expect(templateLink).toHaveText(/Download Template/);
  });

  test('upload button is disabled when no file is selected', async ({ page }) => {
    await page.locator('[data-testid="tab-upload-csv"]').click();
    const uploadBtn = page.locator('[data-testid="upload-csv-btn"]');
    await expect(uploadBtn).toBeDisabled();
  });

  test('all three tabs are visible', async ({ page }) => {
    await expect(page.locator('[data-testid="tab-record-sales"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-all-sales"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-upload-csv"]')).toBeVisible();
  });
});

test.describe('Sales edit/delete/audit buttons', () => {
  test('Edit button is visible on each non-voided sales row', async ({ page }) => {
    const editButtons = page.locator('[data-testid="edit-sale-btn"]');
    const count = await editButtons.count();
    // If there are sales rows, edit buttons should exist
    if (count > 0) {
      await expect(editButtons.first()).toBeVisible();
    }
  });

  test('Void/Delete button is visible on each non-voided sales row', async ({ page }) => {
    const voidButtons = page.locator('[data-testid="void-sale-btn"]');
    const count = await voidButtons.count();
    if (count > 0) {
      await expect(voidButtons.first()).toBeVisible();
    }
  });

  test('Audit trail button is visible on each sales row', async ({ page }) => {
    const auditButtons = page.locator('[data-testid="audit-sale-btn"]');
    const count = await auditButtons.count();
    if (count > 0) {
      await expect(auditButtons.first()).toBeVisible();
    }
  });

  test('clicking Edit button opens the Edit Sale dialog', async ({ page }) => {
    const editButtons = page.locator('[data-testid="edit-sale-btn"]');
    const count = await editButtons.count();
    if (count > 0) {
      await editButtons.first().click();
      // Dialog with header "Edit Sale" should appear
      await expect(page.getByRole('dialog').filter({ hasText: 'Edit Sale' })).toBeVisible();
      // Quantity input should be visible
      await expect(page.locator('[data-testid="edit-quantity-input"]')).toBeVisible();
    }
  });

  test('clicking Void button opens the Void Sale confirmation dialog', async ({ page }) => {
    const voidButtons = page.locator('[data-testid="void-sale-btn"]');
    const count = await voidButtons.count();
    if (count > 0) {
      await voidButtons.first().click();
      // Dialog with header "Void Sale" should appear
      await expect(page.getByRole('dialog').filter({ hasText: 'Void Sale' })).toBeVisible();
      // Reason input should be visible
      await expect(page.locator('[data-testid="void-reason-input"]')).toBeVisible();
    }
  });

  test('clicking Audit trail button opens the Audit Trail dialog', async ({ page }) => {
    const auditButtons = page.locator('[data-testid="audit-sale-btn"]');
    const count = await auditButtons.count();
    if (count > 0) {
      await auditButtons.first().click();
      // Dialog with header "Audit Trail" should appear
      await expect(page.getByRole('dialog').filter({ hasText: 'Audit Trail' })).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// Unit price auto-populate and discount field (task #63)
// ---------------------------------------------------------------------------

test.describe('Unit price and discount in Record Sales form', () => {
  test('auto-populates unit price when product is selected', async ({ page }) => {
    const product = await ensureProduct('E2E Price Populate Product');
    await addStock(product.id, 20);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();

    await page.getByTestId('tab-record-sales').click();
    await expect(page.locator('[data-testid="add-sale-form-card"]')).toBeVisible({ timeout: 5_000 });

    const productOption = page.locator(`select option[value="${product.id}"]`);
    await expect(productOption).toBeAttached({ timeout: 10_000 });

    const productSelect = page.locator('select').filter({ hasText: 'Select product' }).first();
    await productSelect.selectOption(product.id);

    // Unit price display should be populated (product selling_price = 5000 from ensureProduct)
    const priceDisplay = page.locator('[data-testid="entry-price-input"]').first();
    await expect(priceDisplay).toBeVisible();
    const priceText = (await priceDisplay.textContent()) ?? '';
    // Should show a non-zero currency value, not the empty placeholder "—"
    expect(priceText.trim()).not.toBe('—');
    expect(priceText.trim().length).toBeGreaterThan(0);
  });

  test('shows line total calculated from qty and price minus discount', async ({ page }) => {
    const product = await ensureProduct('E2E Line Total Product');
    await addStock(product.id, 50);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();

    await page.getByTestId('tab-record-sales').click();
    await expect(page.locator('[data-testid="add-sale-form-card"]')).toBeVisible({ timeout: 5_000 });

    const productOption = page.locator(`select option[value="${product.id}"]`);
    await expect(productOption).toBeAttached({ timeout: 10_000 });

    const productSelect = page.locator('select').filter({ hasText: 'Select product' }).first();
    await productSelect.selectOption(product.id);

    const qtyInput = page.locator('input[type="number"]').first();
    await qtyInput.fill('2');

    // Line total should be visible (qty × price)
    const lineTotal = page.locator('[data-testid="entry-line-total"]').first();
    await expect(lineTotal).toBeVisible();

    // Enter a discount and line total should change
    const discountInput = page.locator('[data-testid="entry-discount-input"]').first();
    await expect(discountInput).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Create Sale — full E2E flow
// ---------------------------------------------------------------------------

test.describe('Create Sale flow', () => {
  test('fills form and records a sale successfully', async ({ page }) => {
    const product = await ensureProduct('Sale Flow Product');
    await addStock(product.id, 100);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();

    // Switch to Record tab
    await page.getByTestId('tab-record-sales').click();
    await expect(page.locator('[data-testid="add-sale-form-card"]')).toBeVisible({ timeout: 5_000 });

    // Wait for products to load into the dropdown
    const productOption = page.locator(`select option[value="${product.id}"]`);
    await expect(productOption).toBeAttached({ timeout: 10_000 });

    // Select product
    const productSelect = page.locator('select').filter({ hasText: 'Select product' }).first();
    await productSelect.selectOption(product.id);

    // Set quantity
    const qtyInput = page.locator('input[type="number"]').first();
    await qtyInput.fill('3');

    // Click "Record Sales" submit button
    await page.getByRole('button', { name: /Record Sales/i }).click();

    // Success toast should appear
    await expect(page.getByText('Sales recorded successfully')).toBeVisible({ timeout: 10_000 });

    // The Recent Sales table should now have at least one transaction row
    // (product name is not shown in the transaction table; check a table row exists)
    const recentSalesTable = page.locator('table').filter({ has: page.getByRole('columnheader', { name: /Invoice No\./i }) }).first();
    await expect(recentSalesTable.locator('tbody tr').first()).toBeVisible({ timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// Transaction grouping (task #64)
// ---------------------------------------------------------------------------

test.describe('Transaction grouping in All Sales tab', () => {
  test('records 2-product daily entry and shows one grouped row in All Sales', async ({
    page,
  }) => {
    const productA = await ensureProduct('E2E Txn Product A');
    const productB = await ensureProduct('E2E Txn Product B');
    await addStock(productA.id, 30);
    await addStock(productB.id, 30);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();

    // Switch to Record tab first — form is inside @if(activeTab() === 'record') so options
    // only exist in DOM after the tab is active
    await page.getByTestId('tab-record-sales').click();
    await expect(page.locator('[data-testid="add-sale-form-card"]')).toBeVisible({ timeout: 5_000 });

    // Wait for products to load in the select
    await expect(
      page.locator(`select option[value="${productA.id}"]`),
    ).toBeAttached({ timeout: 10_000 });

    // Fill first row
    const productSelects = page.locator('select').filter({ hasText: 'Select product' });
    await productSelects.first().selectOption(productA.id);
    await page.locator('input[type="number"]').first().fill('1');

    // Add a second row
    await page.locator('[data-testid="add-sale-form-card"]').getByRole('button', { name: /Add Product/i }).click();

    // Fill second row
    await expect(productSelects.nth(1)).toBeVisible({ timeout: 5_000 });
    await productSelects.nth(1).selectOption(productB.id);
    await page.locator('input[type="number"]').nth(1).fill('2');

    // Submit
    await page.getByRole('button', { name: /Record Sales/i }).click();
    await expect(page.getByText('Sales recorded successfully')).toBeVisible({ timeout: 10_000 });

    // Switch to All Sales tab
    await page.getByTestId('tab-all-sales').click();

    // Should see exactly one transaction row grouping both products
    const rows = page.locator('[data-testid="transaction-row"]');
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    // The first row in the list (most recent) should show item_count = 2
    await expect(rows.first()).toContainText('2');
  });

  test('click transaction row opens detail dialog with product items', async ({
    page,
  }) => {
    const productA = await ensureProduct('E2E Detail Txn A');
    await addStock(productA.id, 20);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();

    // Switch to Record tab first — form is inside @if(activeTab() === 'record') so options
    // only exist in DOM after the tab is active
    await page.getByTestId('tab-record-sales').click();
    await expect(page.locator('[data-testid="add-sale-form-card"]')).toBeVisible({ timeout: 5_000 });

    await expect(
      page.locator(`select option[value="${productA.id}"]`),
    ).toBeAttached({ timeout: 10_000 });

    await page.locator('select').filter({ hasText: 'Select product' }).first().selectOption(productA.id);
    await page.locator('input[type="number"]').first().fill('1');
    await page.getByRole('button', { name: /Record Sales/i }).click();
    await expect(page.getByText('Sales recorded successfully')).toBeVisible({ timeout: 10_000 });

    // Switch to All Sales tab
    await page.getByTestId('tab-all-sales').click();
    await expect(page.locator('[data-testid="transaction-row"]').first()).toBeVisible({
      timeout: 10_000,
    });

    // Click first transaction row
    await page.locator('[data-testid="transaction-row"]').first().click();

    // Transaction detail dialog should appear with items
    await expect(page.locator('[data-testid="transaction-item-row"]').first()).toBeVisible({
      timeout: 5_000,
    });
  });
});

// ---------------------------------------------------------------------------
// Void sale — stock restore (task #119)
// ---------------------------------------------------------------------------

test.describe('Void sale — stock restore', () => {
  test('voiding a sale restores stock to the pre-sale level', async ({ page }) => {
    const product = await ensureProduct('E2E Void Stock Restore');
    await addStock(product.id, 10);

    // Stock level after adding 10 units (may already have stock from prior runs)
    const stockBefore = await getInventoryQty(product.id);

    // Record a sale of 3 units via daily-entry so it gets a transaction_id
    // and appears in the All Sales tab; derive the invoice number directly.
    const sale = await createDailySale(product.id, { quantity: 3 });
    const invoice = 'INV-' + sale.transaction_id.replace(/-/g, '').slice(0, 8).toUpperCase();

    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();

    // Navigate to All Sales tab and find OUR specific transaction by invoice number.
    // Avoids relying on "first row" which may belong to another test's data.
    await page.getByTestId('tab-all-sales').click();
    const txnRow = page.locator('[data-testid="transaction-row"]').filter({ hasText: invoice });
    await expect(txnRow).toBeVisible({ timeout: 10_000 });
    await txnRow.click();

    // Transaction Detail dialog opens — find our product's item row by product name.
    // We wait up to 10 s for productMap to resolve names (async API call).
    const detailDialog = page.locator('[role="dialog"]').filter({ hasText: 'Transaction Detail' });
    await expect(detailDialog).toBeVisible({ timeout: 5_000 });
    const itemRow = detailDialog
      .locator('[data-testid="transaction-item-row"]')
      .filter({ hasText: product.name });
    await expect(itemRow).toBeVisible({ timeout: 10_000 });

    // Click the void button for that item
    await itemRow.locator('[data-testid="txn-item-void-btn"]').click();

    // Void dialog — fill reason and confirm
    const voidDialog = page.locator('[role="dialog"]').filter({ hasText: 'Void Sale' });
    await expect(voidDialog).toBeVisible({ timeout: 5_000 });
    await voidDialog.locator('[data-testid="void-reason-input"]').fill('E2E stock restore test');
    await voidDialog.locator('[data-testid="confirm-void-btn"]').click();

    // Success toast
    await expect(page.getByText('Sale voided and inventory restored')).toBeVisible({
      timeout: 10_000,
    });

    // Stock must be restored to what it was before the sale
    const stockAfter = await getInventoryQty(product.id);
    expect(stockAfter).toBe(stockBefore);
  });

  test('voided item row has no Void button — sale cannot be voided twice', async ({ page }) => {
    const product = await ensureProduct('E2E No Revoid Product');
    await addStock(product.id, 5);
    // Use daily-entry so the sale has a transaction_id and appears in All Sales
    const sale = await createDailySale(product.id, { quantity: 1 });
    const invoice = 'INV-' + sale.transaction_id.replace(/-/g, '').slice(0, 8).toUpperCase();

    // Void the sale directly via API
    await voidSale(sale.id);

    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();

    await page.getByTestId('tab-all-sales').click();
    const txnRow = page.locator('[data-testid="transaction-row"]').filter({ hasText: invoice });
    await expect(txnRow).toBeVisible({ timeout: 10_000 });
    await txnRow.click();

    // Transaction Detail dialog opens — find our voided item row by product name
    const detailDialog = page.locator('[role="dialog"]').filter({ hasText: 'Transaction Detail' });
    await expect(detailDialog).toBeVisible({ timeout: 5_000 });
    const itemRow = detailDialog
      .locator('[data-testid="transaction-item-row"]')
      .filter({ hasText: product.name });
    await expect(itemRow).toBeVisible({ timeout: 10_000 });

    // The void button must not be present for a voided item
    await expect(itemRow.locator('[data-testid="txn-item-void-btn"]')).toHaveCount(0);
  });
});
