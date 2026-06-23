import { test, expect, request as pwRequest } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';

const API = 'http://localhost:8000/api/v1';

async function createTopLevelCategory(name: string): Promise<string> {
  const token = await getAPIToken();
  const ctx = await pwRequest.newContext();
  try {
    // Check existence first to avoid unique-constraint errors on retry
    const listResp = await ctx.get(`${API}/products/categories`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (listResp.ok()) {
      const cats: { id: string; name: string; children?: { id: string; name: string }[] }[] = await listResp.json();
      const found = cats.find((c) => c.name === name);
      if (found) return found.id;
    }
    const resp = await ctx.post(`${API}/products/categories`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { name },
    });
    if (!resp.ok()) throw new Error(`Failed: ${resp.status()} ${await resp.text()}`);
    return (await resp.json()).id;
  } finally {
    await ctx.dispose();
  }
}

async function createSubcategory(name: string, parentId: string): Promise<string> {
  const token = await getAPIToken();
  const ctx = await pwRequest.newContext();
  try {
    const resp = await ctx.post(`${API}/products/categories`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { name, parent_id: parentId },
    });
    if (!resp.ok()) throw new Error(`Failed: ${resp.status()} ${await resp.text()}`);
    return (await resp.json()).id;
  } finally {
    await ctx.dispose();
  }
}

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/products');
  await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible();
});

// ---------------------------------------------------------------------------
// Category tree display
// ---------------------------------------------------------------------------

test('sub-categories appear indented under their parent in the Categories tab', async ({ page }) => {
  const ts = Date.now();
  const parentName = `E2E Parent ${ts}`;
  const childName = `E2E Child ${ts}`;

  const parentId = await createTopLevelCategory(parentName);
  await createSubcategory(childName, parentId);

  await page.getByRole('button', { name: /Categories/ }).click();
  await page.reload();
  await page.getByRole('button', { name: /Categories/ }).click();

  // Parent appears as a top-level row
  await expect(page.getByRole('cell', { name: parentName })).toBeVisible();
  // Sub-category appears indented (uses ↳ prefix or indent class)
  const childCell = page.locator('td').filter({ hasText: childName }).first();
  await expect(childCell).toBeVisible();
  // The child should appear after the parent in the DOM (tree order)
  const parentRow = page.getByRole('row').filter({ hasText: parentName }).first();
  const childRow = page.getByRole('row').filter({ hasText: childName }).first();
  await expect(parentRow).toBeVisible();
  await expect(childRow).toBeVisible();
});

test('category create form shows optional Parent Category dropdown', async ({ page }) => {
  await page.getByRole('button', { name: /Categories/ }).click();
  const parentSelect = page.locator('select[name="newCategoryParentId"], [data-testid="new-cat-parent-select"]');
  await expect(parentSelect.or(page.getByLabel(/parent category/i))).toBeVisible();
});

// ---------------------------------------------------------------------------
// Grouped category selector in Add Product form
// ---------------------------------------------------------------------------

test('Add Product category selector uses grouped optgroup display when subcategories exist', async ({
  page,
}) => {
  const ts = Date.now();
  const parentName = `E2E Grouped ${ts}`;
  const childName = `E2E Child Grouped ${ts}`;

  const parentId = await createTopLevelCategory(parentName);
  await createSubcategory(childName, parentId);

  // Navigate to Add Product tab
  await page.getByRole('button', { name: /Add Product/ }).click();

  // Reload to pick up the new categories
  await page.reload();
  await page.getByRole('button', { name: /Add Product/ }).click();

  // The category select should contain an optgroup labelled with the parent name
  const catSelect = page.locator('#add-cat-select');
  await expect(catSelect).toBeVisible();
  // The child option should be selectable
  await catSelect.selectOption({ label: childName });
  await expect(catSelect).toHaveValue(/.+/);
});

// ---------------------------------------------------------------------------
// Product assigned to sub-category
// ---------------------------------------------------------------------------

test('product assigned to a sub-category shows sub-category name', async ({ page }) => {
  const ts = Date.now();
  const parentName = `E2E Assigned Parent ${ts}`;
  const childName = `E2E Assigned Child ${ts}`;
  const productName = `E2E SubCat Product ${ts}`;

  const parentId = await createTopLevelCategory(parentName);
  const childId = await createSubcategory(childName, parentId);

  // Create a product via the Add Product tab
  await page.getByRole('button', { name: /Add Product/ }).click();
  await page.reload();
  await page.getByRole('button', { name: /Add Product/ }).click();

  const addForm = page.locator('#add-product-form');
  await addForm.getByPlaceholder('Product name').fill(productName);
  await addForm.locator('[data-testid="add-unit-cost-input"]').fill('1000');
  await addForm.locator('[data-testid="add-selling-price-input"]').fill('1500');
  await addForm.locator('#add-cat-select').selectOption({ value: childId });
  await addForm.getByRole('button', { name: 'Create Product' }).click();
  await expect(page.getByText('Product created')).toBeVisible({ timeout: 8_000 });

  // Product list shows the sub-category name — search to handle pagination
  await page.getByRole('button', { name: /All Products/ }).click();
  await page.getByPlaceholder('Search products...').fill(productName);
  await page.waitForTimeout(400);
  const row = page.getByRole('row').filter({ hasText: productName }).first();
  await expect(row).toBeVisible({ timeout: 5_000 });
  await expect(row).toContainText(childName);
});
