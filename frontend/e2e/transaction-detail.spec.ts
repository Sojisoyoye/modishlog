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

    // Breadcrumb back link
    await expect(page.getByRole('link', { name: /Back to Sales/i })).toBeVisible({ timeout: 8_000 });

    // Invoice number header (INV- prefix)
    await expect(page.getByRole('heading', { level: 1 })).toContainText('INV-', { timeout: 5_000 });

    // Line items table is visible with at least one row
    await expect(page.locator('[data-testid="transaction-item-row"]').first()).toBeVisible({ timeout: 5_000 });
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

    // Set payment method and note
    await dialog.locator('[data-testid="txn-payment-method-select"]').selectOption('transfer');
    await dialog.locator('[data-testid="txn-notes-input"]').fill('E2E test note');

    await dialog.locator('[data-testid="save-txn-edit-btn"]').click();
    await expect(dialog).not.toBeVisible({ timeout: 8_000 });

    // Note is now shown in the header card
    await expect(page.getByText('E2E test note')).toBeVisible({ timeout: 5_000 });
  });

  test('per-item edit dialog opens without notes field', async ({ page }) => {
    const product = await ensureProduct('E2E TxnDetail Item Edit Product');
    await addStock(product.id, 10);
    const { transaction_id } = await createDailySale(product.id);

    await page.goto(`/sales/transactions/${transaction_id}`);
    await expect(page.locator('[data-testid="txn-item-edit-btn"]').first()).toBeVisible({ timeout: 8_000 });
    await page.locator('[data-testid="txn-item-edit-btn"]').first().click();

    const dialog = page.locator('[role="dialog"]').filter({ hasText: /Edit Sale/i });
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    // Notes field must NOT appear in the per-item edit dialog
    await expect(dialog.locator('[data-testid="edit-notes-input"]')).not.toBeVisible();
    await expect(dialog.locator('[data-testid="edit-quantity-input"]')).toBeVisible();
    await expect(dialog.locator('[data-testid="edit-price-input"]')).toBeVisible();
  });

  test('audit trail dialog shows entries after item action', async ({ page }) => {
    const product = await ensureProduct('E2E TxnDetail Audit Product');
    await addStock(product.id, 10);
    const { transaction_id } = await createDailySale(product.id);

    await page.goto(`/sales/transactions/${transaction_id}`);
    await expect(page.locator('[data-testid="txn-item-audit-btn"]').first()).toBeVisible({ timeout: 8_000 });
    await page.locator('[data-testid="txn-item-audit-btn"]').first().click();

    const dialog = page.locator('[role="dialog"]').filter({ hasText: /Audit Trail/i });
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    // At least the creation entry should exist
    await expect(dialog.locator('[data-testid="audit-entry"]').first()).toBeVisible({ timeout: 5_000 });
  });

  test('shows not-found state for unknown transaction ID', async ({ page }) => {
    await page.goto('/sales/transactions/00000000-0000-0000-0000-000000000000');
    await expect(page.getByText('Transaction not found')).toBeVisible({ timeout: 8_000 });
    await expect(page.getByRole('link', { name: /Back to Sales/i })).toBeVisible();
  });
});
