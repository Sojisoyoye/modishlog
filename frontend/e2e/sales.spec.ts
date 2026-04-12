import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

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
    await expect(page.getByRole('button', { name: /Record Sales/i })).toBeVisible();
  });

  test('clicking "Add Row" adds another entry row', async ({ page }) => {
    const initialSelects = await page.locator('select').count();
    await page.getByRole('button', { name: /Add Row/i }).click();
    const newSelects = await page.locator('select').count();
    expect(newSelects).toBeGreaterThan(initialSelects);
  });
});

test.describe('Stock-level validation', () => {
  test('displays stock count next to product dropdown', async ({ page }) => {
    // The stock indicator should appear somewhere in the form area
    // It shows text like "(Stock: <number>)" next to each product select
    const stockIndicator = page.locator('[data-testid="stock-indicator"]').first();
    await expect(stockIndicator).toBeVisible();
    await expect(stockIndicator).toHaveText(/Stock:\s*\d+/);
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

      const submitBtn = page.getByRole('button', { name: /Record Sales/i });
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
