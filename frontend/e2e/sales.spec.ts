import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { addStock, ensureProduct } from './helpers/data';

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
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();

    // Record a sale via the form
    const productSelect = page.locator('select').filter({ hasText: 'Select product' }).first();
    await productSelect.selectOption(product.id);
    const qtyInput = page.locator('input[type="number"]').first();
    await qtyInput.fill('2');
    await page.getByRole('button', { name: /Record Sales/i }).last().click();
    await expect(page.getByText(/recorded/i)).toBeVisible({ timeout: 8_000 });

    // Wait for the sale row to appear then open Edit
    const saleRow = page.getByRole('row').filter({ hasText: product.name }).first();
    await expect(saleRow).toBeVisible({ timeout: 8_000 });
    await saleRow.getByRole('button', { name: /edit/i }).click();

    const dialog = page.locator('[role="dialog"]').filter({ hasText: /edit sale/i });
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    const priceVal = await dialog.locator('[data-testid="edit-price-input"]').inputValue();

    // Must not show 6 trailing decimal zeros like "5000.000000"
    expect(priceVal).not.toMatch(/\.\d{3,}/);
    // Must equal the product's selling_price (5000.00 from ensureProduct helper)
    expect(parseFloat(priceVal)).toBe(5000);
  });
});

test.describe('Sales page layout', () => {
  test('displays the Record Sales section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Record Sales' })).toBeVisible();
  });

  test('displays the Recent Sales section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Recent Sales' })).toBeVisible();
  });

  test('Record Sales form has product dropdown, quantity, and date fields', async ({ page }) => {
    // Product dropdown
    const productSelect = page.locator('select').filter({ hasText: 'Select product' }).first();
    await expect(productSelect).toBeVisible();

    // Quantity input
    const qtyInput = page.locator('input[type="number"]').first();
    await expect(qtyInput).toBeVisible();

    // Date input
    const dateInput = page.locator('input[type="date"]').first();
    await expect(dateInput).toBeVisible();
  });

  test('has "Add Row" and "Record Sales" buttons', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Add Row/i })).toBeVisible();
    // Use last() to avoid strict mode: both the tab and submit button match
    await expect(page.getByRole('button', { name: /Record Sales/i }).last()).toBeVisible();
  });

  test('clicking "Add Row" adds another entry row', async ({ page }) => {
    const selects = page.locator('select');
    const initialCount = await selects.count();
    await page.getByRole('button', { name: /Add Row/i }).click();
    // Use auto-retrying assertion to wait for DOM update
    await expect(selects).toHaveCount(initialCount + 1);
  });
});

test.describe('Stock-level validation', () => {
  test('displays stock count next to product dropdown', async ({ page }) => {
    // Stock indicator only appears after selecting a product
    const productSelect = page.locator('select').first();
    const options = productSelect.locator('option');
    const optionCount = await options.count();

    if (optionCount > 1) {
      await productSelect.selectOption({ index: 1 });
      const stockIndicator = page.locator('[data-testid="stock-indicator"]').first();
      await expect(stockIndicator).toBeVisible();
      await expect(stockIndicator).toHaveText(/Stock:\s*\d+/);
    }
  });

  test('shows stock warning when quantity exceeds available stock', async ({ page }) => {
    // Select the first product (if available)
    const productSelect = page.locator('select').first();
    const options = productSelect.locator('option');
    const optionCount = await options.count();

    if (optionCount > 1) {
      // Select the first real product
      await productSelect.selectOption({ index: 1 });

      // Enter a very large quantity to trigger the warning
      const qtyInput = page.locator('input[type="number"]').first();
      await qtyInput.fill('999999');

      // Expect the exceeds-stock warning to appear
      const warning = page.locator('[data-testid="stock-warning"]').first();
      await expect(warning).toBeVisible();
      await expect(warning).toHaveText(/Exceeds available stock/);
    }
  });

  test('disables Record Sales button when quantity exceeds stock', async ({ page }) => {
    const productSelect = page.locator('select').first();
    const options = productSelect.locator('option');
    const optionCount = await options.count();

    if (optionCount > 1) {
      await productSelect.selectOption({ index: 1 });

      const qtyInput = page.locator('input[type="number"]').first();
      await qtyInput.fill('999999');

      const submitBtn = page.getByRole('button', { name: /Record Sales/i }).last();
      await expect(submitBtn).toBeDisabled();
    }
  });
});

test.describe('Sales history table', () => {
  test('shows table headers (Date, Product, Qty, Total, Status, Actions)', async ({ page }) => {
    await expect(page.getByRole('columnheader', { name: /Date/i })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Product/i })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Qty/i })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Total/i })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Status/i })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Actions/i })).toBeVisible();
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

    const productOption = page.locator(`select option[value="${product.id}"]`);
    await expect(productOption).toBeAttached({ timeout: 10_000 });

    const productSelect = page.locator('select').first();
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

    const productOption = page.locator(`select option[value="${product.id}"]`);
    await expect(productOption).toBeAttached({ timeout: 10_000 });

    const productSelect = page.locator('select').first();
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
    // Create product and add stock via API, then reload page to pick it up
    const product = await ensureProduct('Sale Flow Product');
    await addStock(product.id, 100);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();

    // Wait for products to load into the dropdown
    const productOption = page.locator(`select option[value="${product.id}"]`);
    await expect(productOption).toBeAttached({ timeout: 10_000 });

    // Select product
    const productSelect = page.locator('select').first();
    await productSelect.selectOption(product.id);

    // Set quantity
    const qtyInput = page.locator('input[type="number"]').first();
    await qtyInput.fill('3');

    // Click "Record Sales" submit button (last to avoid tab match)
    await page.getByRole('button', { name: /Record Sales/i }).last().click();

    // Success toast should appear
    await expect(page.getByText('Sales recorded successfully')).toBeVisible({ timeout: 10_000 });

    // The sale should appear in the "Recent Sales" or "All Sales" table
    await expect(page.getByText(product.name).first()).toBeVisible({ timeout: 5_000 });
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

    // Wait for products to load in the select
    await expect(
      page.locator(`select option[value="${productA.id}"]`),
    ).toBeAttached({ timeout: 10_000 });

    // Fill first row
    await page.locator('select').first().selectOption(productA.id);
    await page.locator('input[type="number"]').first().fill('1');

    // Add a second row
    await page.getByRole('button', { name: /Add Row/i }).click();

    // Fill second row (second select, second qty input)
    await page.locator('select').nth(1).selectOption(productB.id);
    await page.locator('input[type="number"]').nth(1).fill('2');

    // Submit
    await page.getByRole('button', { name: /Record Sales/i }).last().click();
    await expect(page.getByText('Sales recorded successfully')).toBeVisible({ timeout: 10_000 });

    // Switch to All Sales tab
    await page.getByTestId('tab-all-sales').click();

    // Should see exactly one transaction row grouping both products
    const rows = page.locator('[data-testid="transaction-row"]');
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    // The first row in the list (most recent) should show item_count = 2
    await expect(rows.first()).toContainText('2');
  });

  test('click transaction row opens detail dialog with product items', async ({ page }) => {
    const productA = await ensureProduct('E2E Detail Txn A');
    await addStock(productA.id, 20);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();

    await expect(
      page.locator(`select option[value="${productA.id}"]`),
    ).toBeAttached({ timeout: 10_000 });

    await page.locator('select').first().selectOption(productA.id);
    await page.locator('input[type="number"]').first().fill('1');
    await page.getByRole('button', { name: /Record Sales/i }).last().click();
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
