import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { addStock, createDailySale, ensureProduct } from './helpers/data';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('Transaction Detail Page', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('navigates to transaction detail page when transaction row is clicked', async ({ page }) => {
    const product = await ensureProduct('E2E TxnDetail Nav Product');
    await addStock(product.id, 20);
    await createDailySale(product.id, { quantity: 2 });

    await page.goto('/sales');
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible();

    await page.getByTestId('tab-all-sales').click();
    const firstTxnRow = page.locator('[data-testid="transaction-row"]').first();
    await expect(firstTxnRow).toBeVisible({ timeout: 10_000 });
    await firstTxnRow.click();

    await expect(page).toHaveURL(/\/sales\/transactions\//, { timeout: 8_000 });
  });

  test('shows breadcrumb, invoice number, and line items table', async ({ page }) => {
    const product = await ensureProduct('E2E TxnDetail View Product');
    await addStock(product.id, 30);
    const { transaction_id } = await createDailySale(product.id, { quantity: 3 });

    await page.goto(`/sales/transactions/${transaction_id}`);

    await expect(page.getByRole('link', { name: /Back to Sales/i })).toBeVisible({ timeout: 8_000 });
    await expect(page.getByRole('heading', { level: 1 })).toContainText('INV-', { timeout: 5_000 });
    await expect(page.locator('[data-testid="transaction-item-row"]').first()).toBeVisible({ timeout: 5_000 });
  });

  test('no edit (pencil) button in action cells', async ({ page }) => {
    const product = await ensureProduct('E2E TxnDetail No Pencil Product');
    await addStock(product.id, 10);
    const { transaction_id } = await createDailySale(product.id);

    await page.goto(`/sales/transactions/${transaction_id}`);
    await expect(page.locator('[data-testid="transaction-item-row"]').first()).toBeVisible({ timeout: 8_000 });

    // The old pencil edit button must not exist anywhere
    await expect(page.locator('[data-testid="txn-item-edit-btn"]')).toHaveCount(0);
  });

  test('clicking product name cell activates inline edit with inputs', async ({ page }) => {
    const product = await ensureProduct('E2E TxnDetail Inline Edit Product');
    await addStock(product.id, 20);
    const { transaction_id } = await createDailySale(product.id, { quantity: 3 });

    await page.goto(`/sales/transactions/${transaction_id}`);
    const row = page.locator('[data-testid="transaction-item-row"]').first();
    await expect(row).toBeVisible({ timeout: 8_000 });

    // Click the product name cell (first td) to activate edit
    await row.locator('td').first().click();

    // Inline inputs should appear
    await expect(page.getByTestId('inline-qty-input')).toBeVisible({ timeout: 3_000 });
    await expect(page.getByTestId('inline-price-input')).toBeVisible();
    await expect(page.getByTestId('inline-discount-input')).toBeVisible();

    // Save and cancel buttons appear; no void button while editing
    await expect(page.getByTestId('inline-save-btn')).toBeVisible();
    await expect(page.getByTestId('inline-cancel-btn')).toBeVisible();
  });

  test('cancel inline edit restores read-only view', async ({ page }) => {
    const product = await ensureProduct('E2E TxnDetail Cancel Edit Product');
    await addStock(product.id, 10);
    const { transaction_id } = await createDailySale(product.id);

    await page.goto(`/sales/transactions/${transaction_id}`);
    const row = page.locator('[data-testid="transaction-item-row"]').first();
    await row.locator('td').first().click();
    await expect(page.getByTestId('inline-qty-input')).toBeVisible({ timeout: 3_000 });

    await page.getByTestId('inline-cancel-btn').click();

    // Inputs gone, void and audit buttons back
    await expect(page.getByTestId('inline-qty-input')).not.toBeVisible();
    await expect(page.getByTestId('txn-item-void-btn').first()).toBeVisible();
    await expect(page.getByTestId('txn-item-audit-btn').first()).toBeVisible();
  });

  test('inline edit: change quantity and save reflects in table', async ({ page }) => {
    const product = await ensureProduct('E2E TxnDetail Save Qty Product');
    await addStock(product.id, 50);
    const { transaction_id } = await createDailySale(product.id, { quantity: 2 });

    await page.goto(`/sales/transactions/${transaction_id}`);
    const row = page.locator('[data-testid="transaction-item-row"]').first();
    await expect(row).toBeVisible({ timeout: 8_000 });
    await row.locator('td').first().click();

    const qtyInput = page.getByTestId('inline-qty-input');
    await expect(qtyInput).toBeVisible({ timeout: 3_000 });
    await qtyInput.fill('5');

    await page.getByTestId('inline-save-btn').click();
    // Row returns to read-only
    await expect(page.getByTestId('inline-qty-input')).not.toBeVisible({ timeout: 8_000 });
    // Updated quantity shows in cell
    await expect(row.locator('td').nth(1)).toContainText('5', { timeout: 5_000 });
  });

  test('Edit Payment & Notes button is visible for active transaction', async ({ page }) => {
    const product = await ensureProduct('E2E TxnDetail Edit Btn Product');
    await addStock(product.id, 10);
    const { transaction_id } = await createDailySale(product.id);

    await page.goto(`/sales/transactions/${transaction_id}`);
    await expect(page.getByTestId('edit-transaction-btn')).toBeVisible({ timeout: 8_000 });
  });

  test('Edit Payment & Notes dialog opens, saves, and reflects updated note', async ({ page }) => {
    const product = await ensureProduct('E2E TxnDetail Edit Txn Product');
    await addStock(product.id, 10);
    const { transaction_id } = await createDailySale(product.id);

    await page.goto(`/sales/transactions/${transaction_id}`);
    await page.getByTestId('edit-transaction-btn').click({ timeout: 8_000 });

    const dialog = page.locator('[role="dialog"]').filter({ hasText: /Edit Payment/i });
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    await dialog.locator('[data-testid="txn-payment-method-select"]').selectOption('transfer');
    await dialog.locator('[data-testid="txn-notes-input"]').fill('E2E test note');

    await dialog.locator('[data-testid="save-txn-edit-btn"]').click();
    await expect(dialog).not.toBeVisible({ timeout: 8_000 });

    await expect(page.getByText('E2E test note')).toBeVisible({ timeout: 5_000 });
  });

  test('audit trail dialog shows entries', async ({ page }) => {
    const product = await ensureProduct('E2E TxnDetail Audit Product');
    await addStock(product.id, 10);
    const { transaction_id } = await createDailySale(product.id);

    await page.goto(`/sales/transactions/${transaction_id}`);
    await expect(page.locator('[data-testid="txn-item-audit-btn"]').first()).toBeVisible({ timeout: 8_000 });
    await page.locator('[data-testid="txn-item-audit-btn"]').first().click();

    const dialog = page.locator('[role="dialog"]').filter({ hasText: /Audit Trail/i });
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    await expect(dialog.locator('[data-testid="audit-entry"]').first()).toBeVisible({ timeout: 5_000 });
  });

  test('shows not-found state for unknown transaction ID', async ({ page }) => {
    await page.goto('/sales/transactions/00000000-0000-0000-0000-000000000000');
    await expect(page.getByText('Transaction not found')).toBeVisible({ timeout: 8_000 });
    await expect(page.getByRole('link', { name: /Back to Sales/i })).toBeVisible();
  });
});
