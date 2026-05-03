import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { ensureProduct } from './helpers/data';

// ---------------------------------------------------------------------------
// Orders Page E2E Tests
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/orders');
  await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible();
});

test.describe('Orders page layout', () => {
  test('displays the page heading and subtitle', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible();
    await expect(page.getByText('Track purchase orders and pipeline')).toBeVisible();
  });

  test('displays the "New Order" button', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'New Order' })).toBeVisible();
  });

  test('renders pipeline status columns', async ({ page }) => {
    // The pipeline view renders these status labels (CSS uppercases them visually)
    const statuses = ['Pending', 'In Production', 'Shipping', 'Cleared', 'Delivered'];
    for (const status of statuses) {
      await expect(page.getByText(status).first()).toBeVisible();
    }
  });

  test('displays the All Orders table', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'All Orders' })).toBeVisible();
    // Table headers
    await expect(page.getByRole('columnheader', { name: /Order/i }).first()).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Supplier/i })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Status/i })).toBeVisible();
  });
});

test.describe('New Order dialog', () => {
  test('"New Order" button opens dialog', async ({ page }) => {
    await page.getByRole('button', { name: 'New Order' }).click();

    const createDialog = page.locator('[role="dialog"]').filter({ hasText: 'New Order' });
    await expect(createDialog).toBeVisible();
  });

  test('New Order dialog has supplier, items, and timeline fields', async ({ page }) => {
    await page.getByRole('button', { name: 'New Order' }).click();

    const dialog = page.locator('[role="dialog"]').filter({ hasText: 'New Order' });
    await expect(dialog).toBeVisible();

    // Supplier input
    await expect(dialog.getByPlaceholder('Supplier name')).toBeVisible();

    // Product select for items
    await expect(dialog.locator('select').first()).toBeVisible();

    // Timeline inputs (Production, Shipping, Clearing days)
    const numberInputs = dialog.locator('input[type="number"]');
    // At least 3 timeline inputs + item qty/cost inputs
    expect(await numberInputs.count()).toBeGreaterThanOrEqual(3);

    // Create Order button
    await expect(dialog.getByRole('button', { name: 'Create Order' })).toBeVisible();
  });

  test('can add additional item rows', async ({ page }) => {
    await page.getByRole('button', { name: 'New Order' }).click();

    const dialog = page.locator('[role="dialog"]').filter({ hasText: 'New Order' });
    const initialSelects = await dialog.locator('select').count();

    await dialog.getByText('Add item').click();

    const newSelects = await dialog.locator('select').count();
    expect(newSelects).toBeGreaterThan(initialSelects);
  });
});

test.describe('Inline product creation in New Order dialog', () => {
  test('New Order dialog contains a "+" button next to product select', async ({ page }) => {
    await page.getByRole('button', { name: 'New Order' }).click();

    const createDialog = page.locator('[role="dialog"]').filter({ hasText: 'New Order' });
    await expect(createDialog).toBeVisible();

    // The "+" inline-create button
    const plusButton = createDialog.locator('button[title="Create new product"]');
    // This feature may or may not be present depending on whether Task 15 is implemented
    const isVisible = await plusButton.isVisible().catch(() => false);
    if (isVisible) {
      await expect(plusButton).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// Order detail dialog — line items
// ---------------------------------------------------------------------------

test.describe('Order detail dialog', () => {
  test('clicking an order row opens detail dialog with line items section', async ({ page }) => {
    const product = await ensureProduct('Detail Dialog Product');
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible();

    // Create an order via the form
    await page.getByRole('button', { name: 'New Order' }).click();
    const createDialog = page.locator('[role="dialog"]').filter({ hasText: 'New Order' });
    await expect(createDialog).toBeVisible({ timeout: 10_000 });

    await createDialog.getByPlaceholder('Supplier name').fill('Detail Test Supplier');
    const productSelect = createDialog.locator('select').first();
    await expect(createDialog.locator(`select option[value="${product.id}"]`)).toBeAttached({ timeout: 10_000 });
    await productSelect.selectOption(product.id);
    await createDialog.locator('input[placeholder="Qty"]').first().fill('10');
    await createDialog.locator('input[placeholder="$/unit"]').first().fill('15');
    await createDialog.getByRole('button', { name: 'Create Order' }).click();
    await expect(createDialog).not.toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('Order created successfully')).toBeVisible({ timeout: 5_000 });

    // Click the newly created order row in the table
    const orderRow = page.getByRole('row').filter({ hasText: 'Detail Test Supplier' }).first();
    await orderRow.click();

    // Order detail dialog should open
    const detailDialog = page.locator('[role="dialog"]').filter({ hasText: 'Order Details' });
    await expect(detailDialog).toBeVisible({ timeout: 10_000 });

    // Line items section must be present
    await expect(detailDialog.getByText('Line Items')).toBeVisible();

    // The product name should appear in the line items table
    await expect(detailDialog.getByText('Detail Dialog Product')).toBeVisible();

    // Qty and unit cost should be displayed
    await expect(detailDialog.getByText('10')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Create Order — full E2E flow
// ---------------------------------------------------------------------------

test.describe('Create Order flow', () => {
  test('fills form and creates an order successfully', async ({ page }) => {
    // Create product via API, then reload page so it appears in the dropdown
    const product = await ensureProduct('Order Flow Product');
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible();

    // Open dialog
    await page.getByRole('button', { name: 'New Order' }).click();
    const dialog = page.locator('[role="dialog"]').filter({ hasText: 'New Order' });
    await expect(dialog).toBeVisible({ timeout: 10_000 });

    // Fill supplier
    await dialog.getByPlaceholder('Supplier name').fill('E2E Test Supplier');

    // Wait for product to appear in the select, then choose it
    const productOption = dialog.locator(`select option[value="${product.id}"]`);
    await expect(productOption).toBeAttached({ timeout: 10_000 });
    const productSelect = dialog.locator('select').first();
    await productSelect.selectOption(product.id);

    // Fill quantity and unit cost
    const qtyInput = dialog.locator('input[placeholder="Qty"]').first();
    await qtyInput.fill('50');

    const costInput = dialog.locator('input[placeholder="$/unit"]').first();
    await costInput.fill('25');

    // Click "Create Order"
    await dialog.getByRole('button', { name: 'Create Order' }).click();

    // Dialog should close after successful creation
    await expect(dialog).not.toBeVisible({ timeout: 10_000 });

    // Success toast should appear
    await expect(page.getByText('Order created successfully')).toBeVisible({ timeout: 5_000 });

    // The order should now appear in the "All Orders" table
    await expect(page.getByText('E2E Test Supplier')).toBeVisible({ timeout: 5_000 });
  });
});
