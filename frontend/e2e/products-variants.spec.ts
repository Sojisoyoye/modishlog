import { test, expect, request as pwRequest } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';
import { ensureCategory } from './helpers/data';

const API = 'http://localhost:8000/api/v1';

let testProductId: string;
let testProductName: string;

/**
 * Create (or reuse) a product with has_variants=true so the Edit dialog
 * will show the variants panel when opened.
 */
async function ensureVariantProduct(): Promise<{ id: string; name: string }> {
  const token = await getAPIToken();
  const cat = await ensureCategory('E2E Variants Category');
  const ctx = await pwRequest.newContext();
  try {
    const name = 'E2E Variant Product';
    // Search first
    const listResp = await ctx.get(
      `${API}/products?search=${encodeURIComponent(name)}&page_size=25`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (listResp.ok()) {
      const data = await listResp.json();
      const items: { id: string; name: string; has_variants?: boolean }[] = Array.isArray(data)
        ? data
        : (data.items ?? []);
      const found = items.find((p) => p.name === name);
      if (found) return { id: found.id, name: found.name };
    }
    const sku = `E2E-VAR-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const resp = await ctx.post(`${API}/products`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name,
        sku,
        unit_cost: '2000.00',
        selling_price: '3500.00',
        currency: 'NGN',
        category_id: cat.id,
        has_variants: true,
      },
    });
    if (!resp.ok()) throw new Error(`Create variant product failed: ${resp.status()} ${await resp.text()}`);
    const product = await resp.json();
    return { id: product.id, name: product.name };
  } finally {
    await ctx.dispose();
  }
}

test.beforeAll(async () => {
  await ensureTestUser();
  const product = await ensureVariantProduct();
  testProductId = product.id;
  testProductName = product.name;
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/products');
  await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible({ timeout: 15_000 });
});

// ---------------------------------------------------------------------------
// Helper: open the Edit Product dialog for the test product
// ---------------------------------------------------------------------------
async function openEditDialog(page: import('@playwright/test').Page): Promise<import('@playwright/test').Locator> {
  // Search for the product to avoid pagination issues
  await page.getByPlaceholder('Search products...').fill(testProductName);
  const row = page.locator('tr').filter({ hasText: testProductName }).first();
  await expect(row).toBeVisible({ timeout: 10_000 });

  await row.locator('button[aria-haspopup="true"]').click();
  const menu = page.locator('[role="menu"]');
  await expect(menu).toBeVisible({ timeout: 5_000 });
  await menu.getByRole('menuitem', { name: 'Edit' }).click();

  const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Edit Product' });
  await expect(dialog).toBeVisible({ timeout: 5_000 });
  return dialog;
}

// ---------------------------------------------------------------------------
// Test 1: Variants panel is visible when has_variants is ON
// ---------------------------------------------------------------------------
test('Edit Product dialog shows variants panel when has_variants is toggled ON', async ({ page }) => {
  const dialog = await openEditDialog(page);

  // The product already has has_variants=true, so the variants panel should be visible
  const variantsPanel = dialog.locator('h4', { hasText: 'Variants' });
  await expect(variantsPanel).toBeVisible({ timeout: 5_000 });

  // The "Add Variant" button should also be visible
  const addVariantBtn = dialog.getByRole('button', { name: /Add Variant/i });
  await expect(addVariantBtn).toBeVisible();
});

// ---------------------------------------------------------------------------
// Test 2: Toggling has_variants ON makes variants panel appear
// ---------------------------------------------------------------------------
test('toggling has_variants ON reveals the variants panel', async ({ page }) => {
  // Create a product without variants for this specific test
  const token = await getAPIToken();
  const cat = await ensureCategory('E2E Variants Toggle Category');
  const ctx = await pwRequest.newContext();
  let noVariantProductName: string;
  try {
    noVariantProductName = `E2E No Variant ${Date.now()}`;
    const sku = `E2E-NV-${Date.now()}`;
    const resp = await ctx.post(`${API}/products`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name: noVariantProductName,
        sku,
        unit_cost: '1000.00',
        selling_price: '2000.00',
        currency: 'NGN',
        category_id: cat.id,
        has_variants: false,
      },
    });
    if (!resp.ok()) throw new Error(`Create no-variant product failed: ${resp.status()} ${await resp.text()}`);
  } finally {
    await ctx.dispose();
  }

  // Search and open Edit dialog for that product
  await page.getByPlaceholder('Search products...').fill(noVariantProductName!);
  const row = page.locator('tr').filter({ hasText: noVariantProductName! }).first();
  await expect(row).toBeVisible({ timeout: 10_000 });
  await row.locator('button[aria-haspopup="true"]').click();
  await page.getByRole('menuitem', { name: 'Edit' }).click();

  const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Edit Product' });
  await expect(dialog).toBeVisible({ timeout: 5_000 });

  // Variants panel should NOT be visible before toggle
  const variantsHeading = dialog.locator('h4', { hasText: 'Variants' });
  await expect(variantsHeading).not.toBeVisible();

  // Toggle has_variants ON
  const hasVariantsCheckbox = dialog.locator('#edit-has-variants');
  await hasVariantsCheckbox.check();

  // Variants panel should now be visible
  await expect(variantsHeading).toBeVisible({ timeout: 3_000 });
  await expect(dialog.getByRole('button', { name: /Add Variant/i })).toBeVisible();
});

// ---------------------------------------------------------------------------
// Test 3: Adding a variant — it appears in the variants list
// ---------------------------------------------------------------------------
test('adding a variant with a name makes it appear in the variant list', async ({ page }) => {
  const dialog = await openEditDialog(page);

  // Wait for variants panel to be visible
  await expect(dialog.locator('h4', { hasText: 'Variants' })).toBeVisible({ timeout: 5_000 });

  const variantName = `Size-XL-${Date.now()}`;

  // Fill the variant name input
  const nameInput = dialog.getByPlaceholder('Variant name *');
  await nameInput.fill(variantName);

  // Click "Add Variant" and wait for the API response
  const addBtn = dialog.getByRole('button', { name: /Add Variant/i });
  await expect(addBtn).toBeEnabled();

  await Promise.all([
    page.waitForResponse(
      (resp) =>
        resp.url().includes(`/products/${testProductId}/variants`) &&
        resp.request().method() === 'POST' &&
        resp.status() === 201,
    ),
    addBtn.click(),
  ]);

  // The new variant should now appear in the table
  const variantRow = dialog.locator('table tbody tr').filter({ hasText: variantName });
  await expect(variantRow).toBeVisible({ timeout: 5_000 });
});

// ---------------------------------------------------------------------------
// Test 4: Deactivating a variant toggles its status to Inactive
// ---------------------------------------------------------------------------
test('deactivating a variant shows it as Inactive', async ({ page }) => {
  // Seed an active variant via the API first
  const token = await getAPIToken();
  const ctx = await pwRequest.newContext();
  let seededVariantName: string;
  try {
    seededVariantName = `E2E-Deactivate-${Date.now()}`;
    const resp = await ctx.post(`${API}/products/${testProductId}/variants`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { name: seededVariantName },
    });
    if (!resp.ok()) throw new Error(`Seed variant failed: ${resp.status()} ${await resp.text()}`);
  } finally {
    await ctx.dispose();
  }

  const dialog = await openEditDialog(page);

  // Wait for the seeded variant row to appear
  const variantRow = dialog.locator('table tbody tr').filter({ hasText: seededVariantName! });
  await expect(variantRow).toBeVisible({ timeout: 8_000 });

  // It should currently show "Active" (use exact regex to avoid matching "Inactive" substring)
  await expect(variantRow.locator('td').filter({ hasText: /^Active$/ }).first()).toBeVisible();

  // Click the Deactivate button on that row and wait for the PATCH response
  const deactivateBtn = variantRow.getByRole('button', { name: /Deactivate/i });
  await expect(deactivateBtn).toBeVisible();

  await Promise.all([
    page.waitForResponse(
      (resp) =>
        resp.url().includes(`/products/${testProductId}/variants`) &&
        resp.request().method() === 'PUT' &&
        resp.status() === 200,
    ),
    deactivateBtn.click(),
  ]);

  // The row should now show "Inactive"
  const inactiveCell = variantRow.locator('td', { hasText: 'Inactive' }).first();
  await expect(inactiveCell).toBeVisible({ timeout: 5_000 });
});

// ---------------------------------------------------------------------------
// Test 5: Disabling has_variants shows the confirm dialog (no window.confirm)
// ---------------------------------------------------------------------------
test('disabling has_variants when variants exist shows a confirm dialog', async ({ page }) => {
  const dialog = await openEditDialog(page);

  // Variants panel should be visible (product has has_variants=true and seeded variants)
  await expect(dialog.locator('h4', { hasText: 'Variants' })).toBeVisible({ timeout: 5_000 });

  // Ensure there is at least one variant visible in the table
  const variantRows = dialog.locator('table tbody tr');
  const count = await variantRows.count();
  // If no variants yet, add one first
  if (count === 0) {
    const nameInput = dialog.getByPlaceholder('Variant name *');
    await nameInput.fill(`Temp-${Date.now()}`);
    const addBtn = dialog.getByRole('button', { name: /Add Variant/i });
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes(`/products/${testProductId}/variants`) &&
          resp.request().method() === 'POST',
      ),
      addBtn.click(),
    ]);
    await expect(dialog.locator('table tbody tr').first()).toBeVisible({ timeout: 5_000 });
  }

  // Toggle has_variants OFF
  const hasVariantsCheckbox = dialog.locator('#edit-has-variants');
  await hasVariantsCheckbox.uncheck();

  // The confirm dialog should appear (NOT window.confirm which blocks the page)
  // Use [role="dialog"] consistent with the rest of the E2E suite (products.spec.ts pattern)
  const confirmDialog = page.locator('[role="dialog"]').filter({ hasText: 'Disable Variants' });
  await expect(confirmDialog).toBeVisible({ timeout: 3_000 });

  // Cancel — variants remain enabled
  const cancelBtn = confirmDialog.getByRole('button', { name: /cancel/i });
  await expect(cancelBtn).toBeVisible();
  await cancelBtn.click();

  // The confirm dialog should be gone and has_variants should still be checked
  await expect(confirmDialog).not.toBeVisible({ timeout: 3_000 });
  await expect(hasVariantsCheckbox).toBeChecked();
});
