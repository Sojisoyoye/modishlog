import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { addStock, createOrder, createSupplier, ensureProduct } from './helpers/data';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/suppliers');
  await expect(page.getByRole('heading', { name: 'Suppliers' })).toBeVisible();
});

test('shows Suppliers heading and Add Supplier button', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Suppliers' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add Supplier' })).toBeVisible();
});

test('opens add supplier dialog and shows required fields', async ({ page }) => {
  await page.getByRole('button', { name: 'Add Supplier' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByPlaceholder('Supplier name')).toBeVisible();
  await expect(page.getByPlaceholder('Contact person')).toBeVisible();
  await expect(page.getByPlaceholder('Email address')).toBeVisible();
  await expect(page.getByPlaceholder('Mobile number')).toBeVisible();
});

test('creates a supplier and shows it in the list', async ({ page }) => {
  const name = `Test Supplier ${Date.now()}`;
  await page.getByRole('button', { name: 'Add Supplier' }).click();
  await page.getByPlaceholder('Supplier name').fill(name);
  await page.getByPlaceholder('Contact person').fill('Jane Doe');
  await page.getByPlaceholder('Email address').fill('jane@test.com');
  await page.getByRole('button', { name: 'Save Supplier' }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden' });
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible({ timeout: 5000 });
});

test('opens supplier detail and shows tabs', async ({ page }) => {
  const name = `Detail Supplier ${Date.now()}`;
  await page.getByRole('button', { name: 'Add Supplier' }).click();
  await page.getByPlaceholder('Supplier name').fill(name);
  await page.getByRole('button', { name: 'Save Supplier' }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden' });
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible({ timeout: 5000 });

  await page.getByRole('cell', { name, exact: true }).click();
  await expect(page.getByRole('tab', { name: 'Purchases' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Stock Report' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Activities' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Ledger' })).toBeVisible();
});

test('can switch between supplier detail tabs', async ({ page }) => {
  const name = `Tab Supplier ${Date.now()}`;
  await page.getByRole('button', { name: 'Add Supplier' }).click();
  await page.getByPlaceholder('Supplier name').fill(name);
  await page.getByRole('button', { name: 'Save Supplier' }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden' });
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible({ timeout: 5000 });

  await page.getByRole('cell', { name, exact: true }).click();
  await page.getByRole('tab', { name: 'Ledger' }).click();
  await expect(page.locator('.pi-spinner')).toHaveCount(0);
  await expect(page.getByRole('table')).toBeVisible();

  await page.getByRole('tab', { name: 'Activities' }).click();
  await expect(page.locator('.pi-spinner')).toHaveCount(0);
  await expect(page.getByText('No activity yet.')).toBeVisible();
});

test('edits a supplier', async ({ page }) => {
  const name = `Edit Me ${Date.now()}`;
  await page.getByRole('button', { name: 'Add Supplier' }).click();
  await page.getByPlaceholder('Supplier name').fill(name);
  await page.getByRole('button', { name: 'Save Supplier' }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden' });
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible({ timeout: 5000 });

  await page.getByTestId(`edit-supplier-${name}`).click();
  await page.getByPlaceholder('Contact person').fill('Updated Contact');
  await page.getByRole('button', { name: 'Save Supplier' }).click();
  await expect(page.getByText('Supplier updated', { exact: true })).toBeVisible({ timeout: 5000 });
});

// ---------------------------------------------------------------------------
// Purchases tab — linked purchase orders (task #123)
// ---------------------------------------------------------------------------
// Note: The backend has no DELETE endpoint for suppliers and the frontend has
// no delete button, so the delete test requested in the task spec cannot be
// implemented without backend + UI changes.
// ---------------------------------------------------------------------------

test.describe('Purchases tab shows linked orders', () => {
  let supplierName: string;
  let supplierId: string;

  test.beforeAll(async () => {
    await ensureTestUser();
    // Create a unique supplier for this describe block
    supplierName = `E2E Purchases Supplier ${Date.now()}`;
    const supplier = await createSupplier(supplierName);
    supplierId = supplier.id;

    // Seed a product + stock + purchase order linked to the supplier
    const product = await ensureProduct('E2E Purchases Tab Product');
    await addStock(product.id, 10);
    await createOrder(product.id, {
      quantity: 5,
      unitCost: '1500.00',
      supplierId,
    });
  });

  test('Purchases tab shows the seeded purchase order', async ({ page }) => {
    // Navigate to suppliers list
    await loginViaUI(page);
    await page.goto('/suppliers');
    await expect(page.getByRole('heading', { name: 'Suppliers' })).toBeVisible();

    // Open supplier detail by clicking the name cell
    await page.getByRole('cell', { name: supplierName, exact: true }).click();

    // Detail panel must open with the supplier's name as header
    await expect(page.getByText(supplierName).first()).toBeVisible({ timeout: 5_000 });

    // Purchases tab should be active by default — assert a table row appears
    await expect(page.getByRole('tab', { name: 'Purchases' })).toBeVisible();

    // Wait for the spinner to disappear and the order to appear
    await expect(page.locator('.pi-spinner')).toHaveCount(0, { timeout: 10_000 });

    // The order row must show status 'ORDERED' (initial state after creation)
    await expect(page.getByRole('cell', { name: 'ORDERED' })).toBeVisible({ timeout: 10_000 });

    // Total amount cell: 5 × 1500 = 7500.00 (formatted by number pipe)
    await expect(page.getByRole('cell', { name: /7[,.]?500/ })).toBeVisible({ timeout: 5_000 });
  });
});
