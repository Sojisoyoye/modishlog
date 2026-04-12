import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

// ---------------------------------------------------------------------------
// Task 15 — Inline product creation inside New Order dialog
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/orders');
  await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible();
});

test('New Order dialog contains a "+" button next to product select', async ({ page }) => {
  await page.getByRole('button', { name: 'New Order' }).click();

  const createDialog = page.locator('[role="dialog"]').filter({ hasText: 'New Order' });
  await expect(createDialog).toBeVisible();

  // The "+" inline-create button (pi-plus-circle icon button)
  const plusButton = createDialog.locator('button[title="Create new product"]');
  await expect(plusButton).toBeVisible();
});

test('clicking "+" opens the Quick Add Product nested dialog', async ({ page }) => {
  await page.getByRole('button', { name: 'New Order' }).click();

  const createDialog = page.locator('[role="dialog"]').filter({ hasText: 'New Order' });
  await createDialog.locator('button[title="Create new product"]').click();

  // The nested dialog should appear
  const inlineDialog = page.locator('[role="dialog"]').filter({ hasText: 'Quick Add Product' });
  await expect(inlineDialog).toBeVisible();
  await expect(inlineDialog.getByPlaceholder('Product name')).toBeVisible();
});

test('inline-created product is auto-selected in the order item row', async ({ page }) => {
  const inlineName = `Inline Product ${Date.now()}`;

  // Open New Order dialog
  await page.getByRole('button', { name: 'New Order' }).click();
  const createDialog = page.locator('[role="dialog"]').filter({ hasText: 'New Order' });

  // Open inline product dialog for the first row
  await createDialog.locator('button[title="Create new product"]').first().click();

  const inlineDialog = page.locator('[role="dialog"]').filter({ hasText: 'Quick Add Product' });
  await expect(inlineDialog).toBeVisible();

  // Fill in the minimal fields
  await inlineDialog.getByPlaceholder('Product name').fill(inlineName);
  const inlineNumbers = inlineDialog.locator('input[type="number"]');
  await inlineNumbers.nth(0).fill('120'); // unit_cost
  await inlineNumbers.nth(1).fill('200'); // selling_price

  await inlineDialog.getByRole('button', { name: 'Save & Select' }).click();

  // Inline dialog closes
  await expect(inlineDialog).not.toBeVisible({ timeout: 10_000 });

  // The product select in the first item row should now show the new product
  const productSelect = createDialog.locator('select').first();

  // Wait for the product to be auto-selected (value must be non-empty)
  await expect(productSelect).not.toHaveValue('');

  // The selected option's text should match the inline product name
  const selectedText = await productSelect.evaluate(
    (sel: HTMLSelectElement) => sel.options[sel.selectedIndex]?.text ?? '',
  );
  expect(selectedText).toContain(inlineName);
});
