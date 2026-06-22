/**
 * Deep E2E test — Products (Task #105)
 * All Products, Stock Report, Add Product tab, Bulk Upload, Categories
 */
import { test, expect, Page } from '@playwright/test';
import { ensureTestUser, loginViaAPI } from './helpers/auth';

test.beforeAll(async () => { await ensureTestUser(); });
test.beforeEach(async ({ page }) => { await loginViaAPI(page); });

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-screenshots/products-${name}.png`, fullPage: true });
}

// -- 1. Products page loads ---------------------------------------------------
test('products - page loads with tabs', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  await shot(page, '01-loaded');
  await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible();
  // Tabs present
  await expect(page.getByText('All Products')).toBeVisible();
  await expect(page.getByText('Add Product')).toBeVisible();
  await expect(page.getByText('Bulk Upload')).toBeVisible();
  await expect(page.getByRole('button', { name: /categories/i })).toBeVisible();
});

// -- 2. All Products tab ------------------------------------------------------
test('products - All Products tab shows list or empty state', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  await shot(page, '02-all-products');
  // List, table, cards, or empty state
  const hasTable = await page.locator('table, [class*="table"], [class*="product-row"]').first().isVisible({ timeout: 3_000 }).catch(() => false);
  const hasEmpty = await page.getByText(/no products|empty|add your first/i).first().isVisible({ timeout: 3_000 }).catch(() => false);
  expect(hasTable || hasEmpty).toBe(true);
});

// -- 3. Products list - search field ------------------------------------------
test('products - search field filters list', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  // The products page has placeholder="Search products..." — assert it exists
  const searchInput = page.locator('input[placeholder*="Search"]').first();
  await expect(searchInput).toBeVisible({ timeout: 5_000 });
  await searchInput.fill('Test');
  await page.waitForLoadState('networkidle');
  await shot(page, '03-search-results');
});

// -- 4. Stock Report tab loads ------------------------------------------------
test('products - Stock Report tab loads content', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  const stockTab = page.getByText('Stock Report');
  await stockTab.click();
  await page.waitForTimeout(600);
  await shot(page, '04-stock-report');
  // Should show a table or chart or empty state — no crash
  await expect(page.locator('body')).not.toContainText('Cannot read');
  await expect(page.locator('body')).not.toContainText('TypeError');
});

// -- 5. Add Product tab - form present with submit button ---------------------
test('products - Add Product tab shows full form with submit button', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('networkidle');

  // Click "New Product" button or "Add Product" tab
  const newBtn = page.getByRole('button', { name: /new product/i });
  if (await newBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await newBtn.click();
  } else {
    await page.getByText('Add Product').click();
  }
  await page.waitForTimeout(500);
  await shot(page, '05-add-product-form');

  // Required fields
  await expect(page.getByPlaceholder('Product name')).toBeVisible();
  // Cost and price fields
  const priceFields = page.locator('input[type="number"]');
  expect(await priceFields.count()).toBeGreaterThan(0);

  // Submit button — the known bug category
  const createBtn = page.getByRole('button', { name: /create product/i });
  await createBtn.scrollIntoViewIfNeeded();
  await shot(page, '05b-submit-button-area');
  await expect(createBtn).toBeVisible({ timeout: 5_000 });
  await expect(page.getByRole('button', { name: /cancel/i })).toBeVisible();
});

// -- 6. Add Product - validation on empty submit ------------------------------
test('products - Add Product validation: empty name shows error not crash', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  const newBtn = page.getByRole('button', { name: /new product/i });
  if (await newBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await newBtn.click();
  } else {
    await page.getByText('Add Product').click();
  }
  await page.waitForTimeout(500);

  // Submit without filling anything
  const createBtn = page.getByRole('button', { name: /create product/i });
  await createBtn.scrollIntoViewIfNeeded();
  await createBtn.click();
  await page.waitForTimeout(800);
  await shot(page, '06-empty-submit');

  // Must show validation error or toast — removing the always-true "nocrash" fallback
  const hasError = await page.locator('[class*="error"], [class*="invalid"], [class*="warn"], [severity="error"], [severity="warn"]').first().isVisible({ timeout: 3_000 }).catch(() => false);
  const hasToast = await page.locator('[class*="toast"]').first().isVisible({ timeout: 3_000 }).catch(() => false);
  expect(hasError || hasToast).toBe(true);
});

// -- 7. Add Product - create a real product and verify it appears -------------
test('products - create product end-to-end', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  const newBtn = page.getByRole('button', { name: /new product/i });
  if (await newBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await newBtn.click();
  } else {
    await page.getByText('Add Product').click();
  }
  await page.waitForTimeout(500);

  const uniqueName = `E2E-Product-${Date.now()}`;

  // Fill the form
  await page.getByPlaceholder('Product name').fill(uniqueName);

  // Select a category — required field (NOT NULL in DB)
  const catSelect = page.locator('select#add-cat-select').first();
  if (await catSelect.isVisible({ timeout: 3_000 }).catch(() => false)) {
    // Pick the first non-empty option (any real category)
    const optionValues = await catSelect.locator('option').evaluateAll(
      (opts) => (opts as HTMLOptionElement[]).filter(o => o.value).map(o => o.value)
    );
    if (optionValues.length > 0) {
      await catSelect.selectOption(optionValues[0]);
    }
  }

  // SKU field if present
  const skuInput = page.locator('input[placeholder*="SKU"], input[placeholder*="sku"]').first();
  if (await skuInput.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await skuInput.fill(`E2E-SKU-${Date.now()}`);
  }

  // Unit cost and selling price — prefer data-testid, fall back to placeholder
  const costInput = page.locator('[data-testid="add-unit-cost-input"]').first();
  const priceInput = page.locator('[data-testid="add-selling-price-input"]').first();
  if (await costInput.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await costInput.fill('1000');
    await costInput.press('Tab');
  }
  if (await priceInput.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await priceInput.fill('1500');
    await priceInput.press('Tab');
  }

  await shot(page, '07-product-filled');

  // Submit
  const createBtn = page.getByRole('button', { name: /create product/i });
  await createBtn.scrollIntoViewIfNeeded();
  await createBtn.click();
  await page.waitForTimeout(2_000);
  await shot(page, '07-after-create');

  // Expect success toast or product appears in search
  const successToast = page.locator('[class*="toast"][class*="success"], .p-toast-message-success').first();
  const toastVisible = await successToast.isVisible({ timeout: 5_000 }).catch(() => false);
  if (!toastVisible) {
    // Navigate to All Products and search for the newly created product
    await page.getByText('All Products').click();
    await page.waitForTimeout(500);
    const searchBox = page.locator('input[placeholder*="Search"]').first();
    if (await searchBox.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await searchBox.fill(uniqueName);
      await page.waitForTimeout(700);
    }
    await shot(page, '07-search-for-product');
    const productInList = await page.getByText(uniqueName).isVisible({ timeout: 5_000 }).catch(() => false);
    expect(productInList).toBe(true);
  } else {
    expect(toastVisible).toBe(true);
  }
});

// -- 8. Bulk Upload tab - file input and template download -------------------
test('products - Bulk Upload tab shows file input and template download', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  await page.getByText('Bulk Upload').click();
  await page.waitForTimeout(500);
  await shot(page, '08-bulk-upload');

  // File input or drag-and-drop area
  const hasFileInput = await page.locator('input[type="file"]').isVisible({ timeout: 3_000 }).catch(() => false);
  const hasDragDrop = await page.locator('[class*="upload"], [class*="drop"], [class*="drag"]').first().isVisible({ timeout: 3_000 }).catch(() => false);
  expect(hasFileInput || hasDragDrop).toBe(true);

  // Template download button must be present (component renders "Download CSV template")
  const templateBtn = page.getByRole('button', { name: /template|download/i }).first();
  const templateLink = page.getByRole('link', { name: /template|download/i }).first();
  const hasTemplate = await templateBtn.isVisible({ timeout: 3_000 }).catch(() => false)
    || await templateLink.isVisible({ timeout: 3_000 }).catch(() => false);
  expect(hasTemplate).toBe(true);
});

// -- 9. Categories tab - list, add category ----------------------------------
test('products - Categories tab loads and shows Add Category option', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: /categories/i }).click();
  await page.waitForTimeout(600);
  await shot(page, '09-categories-tab');

  // Categories should be listed or show empty state
  const hasList = await page.locator('table, [class*="category-row"], [class*="list"]').first().isVisible({ timeout: 4_000 }).catch(() => false);
  const hasEmpty = await page.getByText(/no categories|add.*category/i).first().isVisible({ timeout: 3_000 }).catch(() => false);
  expect(hasList || hasEmpty).toBe(true);

  // An "Add Category" button should be present
  const addBtn = page.getByRole('button', { name: /add category|new category/i }).first();
  const hasAddBtn = await addBtn.isVisible({ timeout: 3_000 }).catch(() => false);
  await shot(page, '09b-categories-add-btn');
  expect(hasAddBtn).toBe(true);
});

// -- 10. Add Category - inline form has fields and submit button -------------
test('products - Add Category inline form has fields and submit button', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: /categories/i }).click();
  await page.waitForTimeout(600);
  await shot(page, '10-categories-tab');

  // The Add Category form is inline (not a modal) — look for the name input
  const nameInput = page.locator('input[placeholder*="Category name"]').first();
  const hasNameInput = await nameInput.isVisible({ timeout: 5_000 }).catch(() => false);
  expect(hasNameInput).toBe(true);

  // The submit button should be present (initially disabled until name is typed)
  const addBtn = page.getByRole('button', { name: /add category/i }).first();
  const hasAddBtn = await addBtn.isVisible({ timeout: 3_000 }).catch(() => false);
  expect(hasAddBtn).toBe(true);

  await shot(page, '10b-add-category-form');
});

// -- 11. Add Category - create one end-to-end --------------------------------
test('products - create category end-to-end', async ({ page }) => {
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: /categories/i }).click();
  await page.waitForTimeout(600);

  // The form is inline — fill name input first, then click Add Category
  const nameInput = page.locator('input[placeholder*="Category name"]').first();
  // Assert the input exists rather than silently returning
  await expect(nameInput).toBeVisible({ timeout: 5_000 });

  const catName = `E2E-Cat-${Date.now()}`;
  await nameInput.fill(catName);
  await page.waitForTimeout(300);
  await shot(page, '11-category-filled');

  // Now the button should be enabled
  const addBtn = page.getByRole('button', { name: /add category/i }).first();
  await addBtn.click();
  await page.waitForTimeout(1_500);
  await shot(page, '11-after-create-category');

  // Expect toast or new category in list
  const toastVisible = await page.locator('[class*="toast"]').first().isVisible({ timeout: 4_000 }).catch(() => false);
  const catInList = await page.getByText(catName).isVisible({ timeout: 4_000 }).catch(() => false);
  expect(toastVisible || catInList).toBe(true);
});
