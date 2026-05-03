import { test, expect, request as pwRequest } from '@playwright/test';
import { ensureTestUser, loginViaUI, E2E_EMAIL, E2E_PASSWORD } from './helpers/auth';
import { ensureCategory, ensureProductInCategory } from './helpers/data';

const API = 'http://localhost:8000/api/v1';

// Create the test user once for this suite
test.beforeAll(async () => {
  await ensureTestUser();
});

// Authenticate and land on /products before every test
test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/products');
  await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible();
});

// ---------------------------------------------------------------------------
// Products page basics
// ---------------------------------------------------------------------------

test('shows the Products page heading and New Product button', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'New Product' })).toBeVisible();
});

test('displays product tabs (All Products, Stock Report, Add Product, Categories)', async ({
  page,
}) => {
  await expect(page.getByRole('button', { name: /All Products/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /Stock Report/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /Add Product/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /Categories/ })).toBeVisible();
});

// ---------------------------------------------------------------------------
// Price decimal display in Edit Product dialog (task #59)
// ---------------------------------------------------------------------------

test.describe('Edit Product price decimal display', () => {
  test('unit cost and selling price inputs show at most 2 decimal places', async ({ page }) => {
    // Create a product via the UI so it appears in the table
    const name = `E2E Decimal ${Date.now()}`;
    await page.getByRole('button', { name: 'New Product' }).click();
    const addForm = page.locator('#add-product-form');
    await addForm.getByPlaceholder('Product name').fill(name);
    const nums = addForm.locator('input[type="number"]');
    await nums.nth(0).fill('10500');  // unit_cost
    await nums.nth(1).fill('15500');  // selling_price
    // Submit button inside the add form is labelled "Create Product"
    await addForm.getByRole('button', { name: 'Create Product' }).click();
    await expect(page.getByText('Product created')).toBeVisible({ timeout: 5_000 });

    // Wait for the product row to be visible before interacting
    const row = page.getByRole('row').filter({ hasText: name }).first();
    await expect(row).toBeVisible({ timeout: 5_000 });

    // Open the action menu and click Edit
    await row.getByRole('button', { name: /actions/i }).click();
    await page.getByRole('menuitem', { name: 'Edit' }).click();

    const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Edit Product' });
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    // Read raw input values via stable data-testid selectors
    const costVal = await dialog.locator('[data-testid="edit-unit-cost-input"]').inputValue();
    const priceVal = await dialog.locator('[data-testid="edit-selling-price-input"]').inputValue();

    // Must not have 3+ decimal places (e.g. "10500.000000" from Pydantic Decimal)
    expect(costVal).not.toMatch(/\.\d{3,}/);
    expect(priceVal).not.toMatch(/\.\d{3,}/);
    // Must equal the values entered (no precision loss, no zeroing)
    expect(parseFloat(costVal)).toBe(10500);
    expect(parseFloat(priceVal)).toBe(15500);
  });
});

// ---------------------------------------------------------------------------
// Action menu visibility (must not be clipped by overflow:auto container)
// ---------------------------------------------------------------------------

test('product action menu is visible and not clipped by the table container', async ({ page }) => {
  // Create a product so there is at least one row
  const name = `E2E MenuVis ${Date.now()}`;
  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');
  await addForm.getByPlaceholder('Product name').fill(name);
  const nums = addForm.locator('input[type="number"]');
  await nums.nth(0).fill('100');
  await nums.nth(1).fill('180');
  await addForm.getByRole('button', { name: 'Create Product' }).click();
  await expect(page.getByText(name)).toBeVisible({ timeout: 10_000 });

  // Click the ellipsis button on the product row
  const row = page.locator('tr').filter({ hasText: name });
  await row.locator('button[aria-haspopup="true"]').click();

  // The menu must be visible — rendered via fixed positioning outside the overflow container
  const menu = page.locator('[role="menu"]').filter({ hasText: 'Edit' });
  await expect(menu).toBeVisible({ timeout: 3_000 });
  await expect(menu.getByRole('button', { name: 'Edit' })).toBeVisible();
  await expect(menu.getByRole('button', { name: 'Delete' })).toBeVisible();

  // Verify the menu is not clipped: its bounding box must be fully within the viewport
  const box = await menu.boundingBox();
  const viewport = page.viewportSize()!;
  expect(box).not.toBeNull();
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width);
});

// ---------------------------------------------------------------------------
// Currency formatting — prices always show 2 decimal places with thousands sep
// ---------------------------------------------------------------------------

test('product table displays prices formatted to 2 decimal places', async ({ page }) => {
  const name = `E2E Fmt ${Date.now()}`;

  // Create a product with a cost that would show differently at 0dp vs 2dp
  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');
  await addForm.getByPlaceholder('Product name').fill(name);
  const nums = addForm.locator('input[type="number"]');
  await nums.nth(0).fill('10200');    // unit_cost — should display as 10,200.00
  await nums.nth(1).fill('14500.50'); // selling_price — should display as 14,500.50
  await addForm.getByRole('button', { name: 'Create Product' }).click();
  await expect(page.getByText(name)).toBeVisible({ timeout: 10_000 });

  // Locate the product row and check the formatted price cells
  const row = page.locator('tr').filter({ hasText: name });
  // Unit cost: 10,200.00 — must contain the decimal separator
  await expect(row).toContainText('10,200.00');
  // Selling price: 14,500.50
  await expect(row).toContainText('14,500.50');
});

test('add product form inputs have 0.00 placeholder and accept decimals', async ({ page }) => {
  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');
  const nums = addForm.locator('input[type="number"]');
  await expect(nums.nth(0)).toHaveAttribute('placeholder', '0.00');
  await expect(nums.nth(1)).toHaveAttribute('placeholder', '0.00');
  await expect(nums.nth(0)).toHaveAttribute('step', '0.01');
  await expect(nums.nth(1)).toHaveAttribute('step', '0.01');
});

// ---------------------------------------------------------------------------
// Profit margin indicator on add/edit form
// ---------------------------------------------------------------------------

test('Add Product form shows profit margin % when cost and price are filled', async ({ page }) => {
  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');
  const nums = addForm.locator('input[type="number"]');

  // Fill cost=100, price=150 → margin = (150-100)/150*100 = 33.3%
  await nums.nth(0).fill('100');
  await nums.nth(1).fill('150');

  const marginBadge = addForm.locator('[data-testid="add-margin"]');
  await expect(marginBadge).toBeVisible();
  await expect(marginBadge).toContainText('33.3%');
});

test('Add Product form margin indicator is green for positive margin, red for negative', async ({
  page,
}) => {
  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');
  const nums = addForm.locator('input[type="number"]');
  const marginBadge = addForm.locator('[data-testid="add-margin"]');

  // Positive margin → green
  await nums.nth(0).fill('100');
  await nums.nth(1).fill('150');
  await expect(marginBadge).toBeVisible();
  await expect(marginBadge).toHaveClass(/text-green/);

  // Negative margin (price < cost) → red
  await nums.nth(1).fill('80');
  await expect(marginBadge).toHaveClass(/text-red/);
});

test('Edit Product dialog shows profit margin % for existing product', async ({ page }) => {
  const name = `E2E Margin ${Date.now()}`;

  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');
  await addForm.getByPlaceholder('Product name').fill(name);
  const nums = addForm.locator('input[type="number"]');
  await nums.nth(0).fill('200');
  await nums.nth(1).fill('400');
  await addForm.getByRole('button', { name: 'Create Product' }).click();
  await expect(page.getByText(name)).toBeVisible({ timeout: 10_000 });

  // Open edit dialog via action menu
  const row = page.locator('tr').filter({ hasText: name });
  await row.locator('button[aria-haspopup="true"]').click();
  await page.locator('[role="menu"]').filter({ hasText: 'Edit' }).getByRole('button', { name: 'Edit' }).click();

  const editDialog = page.locator('[role="dialog"]').filter({ hasText: 'Edit Product' });
  await expect(editDialog).toBeVisible();

  // margin = (400-200)/400*100 = 50.0%
  const marginBadge = editDialog.locator('[data-testid="edit-margin"]');
  await expect(marginBadge).toBeVisible();
  await expect(marginBadge).toContainText('50.0%');
});

// ---------------------------------------------------------------------------
// Grid / List view toggle
// ---------------------------------------------------------------------------

test('toggles between grid and list view', async ({ page }) => {
  // Default is list view (table should be visible)
  const listToggle = page.locator('button[title="List view"]');
  const gridToggle = page.locator('button[title="Grid view"]');

  await expect(listToggle).toBeVisible();
  await expect(gridToggle).toBeVisible();

  // Click grid view
  await gridToggle.click();
  await expect(gridToggle).toHaveClass(/bg-primary/);

  // Click list view
  await listToggle.click();
  await expect(listToggle).toHaveClass(/bg-primary/);
});

// ---------------------------------------------------------------------------
// Search filter
// ---------------------------------------------------------------------------

test('search input filters products', async ({ page }) => {
  const searchInput = page.getByPlaceholder('Search products...');
  await expect(searchInput).toBeVisible();

  // Type a search that is unlikely to match anything
  await searchInput.fill('zzzznonexistent');
  // Wait for filtering to apply
  await page.waitForTimeout(500);

  // The table body should either show "No products found" or have zero data rows
  const noResults = page.getByText(/No products/i);
  const isNoResults = await noResults.isVisible().catch(() => false);
  if (!isNoResults) {
    // If the table just becomes empty, at least the rows should be less
    const rows = await page.locator('tbody tr').count();
    // With a nonsense search, there should be very few or zero rows
    expect(rows).toBeLessThanOrEqual(1);
  }
});

// ---------------------------------------------------------------------------
// New Product button opens add form
// ---------------------------------------------------------------------------

test('"New Product" button switches to Add Product tab', async ({ page }) => {
  await page.getByRole('button', { name: 'New Product' }).click();

  // The add product form should be visible
  const addForm = page.locator('#add-product-form');
  await expect(addForm).toBeVisible();
  await expect(addForm.getByPlaceholder('Product name')).toBeVisible();
});

// ---------------------------------------------------------------------------
// Create product flow
// ---------------------------------------------------------------------------

test('can create a product without a category', async ({ page }) => {
  const name = `E2E Product ${Date.now()}`;

  // Open Add Product tab via the "New Product" button
  await page.getByRole('button', { name: 'New Product' }).click();

  const addForm = page.locator('#add-product-form');
  await expect(addForm).toBeVisible();

  // Fill form
  await addForm.getByPlaceholder('Product name').fill(name);
  const numberInputs = addForm.locator('input[type="number"]');
  await numberInputs.nth(0).fill('200'); // unit_cost
  await numberInputs.nth(1).fill('350'); // selling_price

  // Submit
  await addForm.getByRole('button', { name: 'Create Product' }).click();

  // Switches back to All Products tab; new product appears
  await expect(page.getByText(name)).toBeVisible({ timeout: 10_000 });
});

// ---------------------------------------------------------------------------
// Edit a product
// ---------------------------------------------------------------------------

test('can edit a product name and price', async ({ page }) => {
  const name = `E2E Edit ${Date.now()}`;
  const updatedName = `${name} Updated`;

  // Create product first via Add tab
  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');
  await addForm.getByPlaceholder('Product name').fill(name);
  const createNumbers = addForm.locator('input[type="number"]');
  await createNumbers.nth(0).fill('100');
  await createNumbers.nth(1).fill('180');
  await addForm.getByRole('button', { name: 'Create Product' }).click();
  await expect(page.getByText(name)).toBeVisible({ timeout: 10_000 });

  // Open the actions menu for this product row
  const row = page.locator('tr').filter({ hasText: name });
  await row.locator('button').last().click(); // ellipsis button

  // Click Edit in the dropdown
  await page.locator('button[title="Edit product"]').click();

  // The edit dialog should open
  const editDialog = page.locator('[role="dialog"]').filter({ hasText: 'Edit Product' });
  await expect(editDialog).toBeVisible();

  const nameInput = editDialog.locator('input').first();
  await nameInput.clear();
  await nameInput.fill(updatedName);

  await editDialog.getByRole('button', { name: 'Save Changes' }).click();

  await expect(page.getByText(updatedName)).toBeVisible({ timeout: 10_000 });
});

// ---------------------------------------------------------------------------
// Delete a product
// ---------------------------------------------------------------------------

test('can delete a product', async ({ page }) => {
  const name = `E2E Delete ${Date.now()}`;

  // Create product via Add tab
  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');
  await addForm.getByPlaceholder('Product name').fill(name);
  const nums = addForm.locator('input[type="number"]');
  await nums.nth(0).fill('50');
  await nums.nth(1).fill('90');
  await addForm.getByRole('button', { name: 'Create Product' }).click();
  await expect(page.getByText(name)).toBeVisible({ timeout: 10_000 });

  // Open actions menu then click Delete
  const row = page.locator('tr').filter({ hasText: name });
  await row.locator('button').last().click(); // ellipsis button
  await page.locator('button[title="Delete product"]').click();

  // Custom confirm dialog appears — click Delete to confirm
  const confirmDialog = page.locator('[role="dialog"]').filter({ hasText: 'Delete Product' });
  await expect(confirmDialog).toBeVisible({ timeout: 5_000 });
  await confirmDialog.getByRole('button', { name: 'Delete' }).click();

  // Row should disappear
  await expect(page.getByText(name)).not.toBeVisible({ timeout: 10_000 });
});

// ---------------------------------------------------------------------------
// Category management tab
// ---------------------------------------------------------------------------

test('Categories tab shows category list', async ({ page }) => {
  await page.getByRole('button', { name: /Categories/ }).click();
  // The categories tab should be active and show a form or list
  await page.waitForTimeout(1000);
  // Either "Add Category" or an existing category list is visible
  const hasCategoryContent =
    (await page.getByText(/category/i).count()) > 0 ||
    (await page.getByPlaceholder('Category name').isVisible().catch(() => false));
  expect(hasCategoryContent).toBeTruthy();
});

// ---------------------------------------------------------------------------
// Inline category creation inside Add Product tab
// ---------------------------------------------------------------------------

test('Add Product tab shows a "New category" toggle', async ({ page }) => {
  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');
  await expect(addForm).toBeVisible();
  await expect(addForm.getByRole('button', { name: /New category/i })).toBeVisible();
});

test('clicking "New category" reveals the inline input', async ({ page }) => {
  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');

  await addForm.getByRole('button', { name: /New category/i }).click();

  // Inline input and Save category button should appear
  await expect(addForm.getByPlaceholder('Category name')).toBeVisible();
  await expect(addForm.locator('button[title="Save category"]')).toBeVisible();

  // The category select should be hidden
  await expect(addForm.locator('#add-cat-select')).not.toBeVisible();
});

test('can create a category inline and it is auto-selected', async ({ page }) => {
  const catName = `E2E Cat ${Date.now()}`;

  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');

  // Open inline form
  await addForm.getByRole('button', { name: /New category/i }).click();
  await addForm.getByPlaceholder('Category name').fill(catName);
  await addForm.locator('button[title="Save category"]').click();

  // Inline form closes, select reappears with new category auto-selected
  await expect(addForm.getByPlaceholder('Category name')).not.toBeVisible({ timeout: 8_000 });
  await expect(addForm.locator('#add-cat-select')).toBeVisible();

  const selectedText = await addForm.locator('#add-cat-select').evaluate(
    (sel: HTMLSelectElement) => sel.options[sel.selectedIndex]?.text ?? '',
  );
  expect(selectedText).toContain(catName);
});

test('can create a product with the inline-created category', async ({ page }) => {
  const catName = `E2E Cat ${Date.now()}`;
  const productName = `E2E Product Cat ${Date.now()}`;

  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');

  // Create category inline
  await addForm.getByRole('button', { name: /New category/i }).click();
  await addForm.getByPlaceholder('Category name').fill(catName);
  await addForm.locator('button[title="Save category"]').click();
  await expect(addForm.locator('#add-cat-select')).toBeVisible({ timeout: 8_000 });

  // Fill product details
  await addForm.getByPlaceholder('Product name').fill(productName);
  const prodNums = addForm.locator('input[type="number"]');
  await prodNums.nth(0).fill('75');
  await prodNums.nth(1).fill('120');

  await addForm.getByRole('button', { name: 'Create Product' }).click();

  // Product appears in the list
  await expect(page.getByText(productName)).toBeVisible({ timeout: 10_000 });
});

// ---------------------------------------------------------------------------
// Inline alert banner — delete category confirmation
// ---------------------------------------------------------------------------

test('shows inline confirm banner when deleting a category (cancel keeps category)', async ({ page }) => {
  const catName = `E2E ConfirmCat ${Date.now()}`;

  // Create a category first via the Categories tab
  await page.getByRole('button', { name: /Categories/ }).click();
  await expect(page.getByPlaceholder('Category name').first()).toBeVisible();

  await page.getByPlaceholder('Category name').first().fill(catName);
  await page.getByRole('button', { name: 'Add Category' }).click();
  await expect(page.getByText(catName)).toBeVisible({ timeout: 8_000 });

  // Click the trash icon — an inline alert banner with Cancel/Delete appears (no modal)
  await page.locator('tr').filter({ hasText: catName }).locator('button[title="Delete category"]').click();

  // Inline banner appears inside the categories tab (scoped to app-alert-banner element)
  const confirmBanner = page.locator('app-alert-banner');
  await expect(confirmBanner.getByRole('button', { name: 'Cancel' })).toBeVisible({ timeout: 3_000 });
  await expect(confirmBanner.getByRole('button', { name: 'Delete' })).toBeVisible({ timeout: 3_000 });
  await expect(page.getByText(catName)).toBeVisible();

  // Click Cancel — banner dismisses, category still in table
  await confirmBanner.getByRole('button', { name: 'Cancel' }).click();
  await expect(confirmBanner).not.toBeVisible({ timeout: 3_000 });
  await expect(page.getByText(catName)).toBeVisible();
});

test('deletes category after confirming in inline banner', async ({ page }) => {
  const catName = `E2E DeleteCat ${Date.now()}`;

  // Create a category via the Categories tab
  await page.getByRole('button', { name: /Categories/ }).click();
  await expect(page.getByPlaceholder('Category name').first()).toBeVisible();

  await page.getByPlaceholder('Category name').first().fill(catName);
  await page.getByRole('button', { name: 'Add Category' }).click();
  await expect(page.getByText(catName)).toBeVisible({ timeout: 8_000 });

  // Click the trash icon — inline alert banner appears
  await page.locator('tr').filter({ hasText: catName }).locator('button[title="Delete category"]').click();
  const confirmBanner = page.locator('app-alert-banner');
  await expect(confirmBanner.getByRole('button', { name: 'Delete' })).toBeVisible({ timeout: 3_000 });

  // Click Delete — category is removed from the table
  await confirmBanner.getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText(catName)).not.toBeVisible({ timeout: 8_000 });
});

// ---------------------------------------------------------------------------
// API-level: products endpoint returns image_url field
// ---------------------------------------------------------------------------

test('GET /api/v1/products returns image_url field in items', async () => {
  const ctx = await pwRequest.newContext();
  const loginResp = await ctx.post(`${API}/auth/login`, {
    data: { email: E2E_EMAIL, password: E2E_PASSWORD },
  });
  const { access_token } = await loginResp.json();

  const resp = await ctx.get(`${API}/products`, {
    headers: { Authorization: `Bearer ${access_token}` },
  });
  expect(resp.status()).toBe(200);

  const body = await resp.json();
  expect(body).toHaveProperty('items');
  // Each item should have image_url key (may be null, but the key must exist)
  if (body.items.length > 0) {
    expect(body.items[0]).toHaveProperty('image_url');
  }

  await ctx.dispose();
});

// ---------------------------------------------------------------------------
// Friendly 409 error when deleting a category with products (task #60)
// ---------------------------------------------------------------------------

test.describe('Category delete with linked products', () => {
  test('shows friendly warning toast when deleting a category that has products', async ({ page }) => {
    // Seed: category + product assigned to it, both via API
    const category = await ensureCategory(`E2E Cat Delete ${Date.now()}`);
    await ensureProductInCategory(category.id, `E2E Cat Product ${Date.now()}`);

    // Reload so the freshly-seeded category appears (beforeEach navigated before API seed)
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible();

    // Switch to the Categories tab
    await page.getByRole('button', { name: /Categories/i }).click();

    // Wait for the category row to appear
    const categoryRow = page.getByRole('row').filter({ hasText: category.name }).first();
    await expect(categoryRow).toBeVisible({ timeout: 8_000 });

    // Click the trash icon to initiate delete
    await categoryRow.locator('button[title="Delete category"]').click();

    // Confirm in the inline alert banner that appears
    const alertBanner = page.locator('app-alert-banner');
    await expect(alertBanner).toBeVisible({ timeout: 5_000 });
    await alertBanner.getByRole('button', { name: 'Delete' }).click();

    // A WARN toast (amber) must appear — severity='warn' → PrimeNG class p-toast-message-warn
    const toast = page.locator('.p-toast-message');
    await expect(toast).toBeVisible({ timeout: 8_000 });
    await expect(toast).toHaveClass(/p-toast-message-warn/);
    // Message must mention products and guide the user
    await expect(page.getByText(/still has|Move or delete|before removing/i)).toBeVisible({ timeout: 5_000 });

    // Category must still be in the table (not deleted)
    await expect(categoryRow).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Category editing (task #61)
// ---------------------------------------------------------------------------

test.describe('Category editing', () => {
  test('pencil button opens edit dialog pre-filled with current values', async ({ page }) => {
    const catName = `E2E Edit Cat ${Date.now()}`;

    // Create category via the UI form
    await page.getByRole('button', { name: /Categories/ }).click();
    await page.getByPlaceholder('Category name').fill(catName);
    await page.getByPlaceholder('Description (optional)').fill('Original desc');
    await page.getByRole('button', { name: 'Add Category' }).click();
    await expect(page.getByText(catName)).toBeVisible({ timeout: 5_000 });

    // Click the pencil (edit) button on the new category row
    const catRow = page.locator('tr').filter({ hasText: catName });
    await catRow.locator('button[title="Edit category"]').click();

    const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Edit Category' });
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    // Fields must be pre-filled with current values
    await expect(dialog.locator('#cat-edit-name')).toHaveValue(catName);
    await expect(dialog.locator('#cat-edit-description')).toHaveValue('Original desc');
  });

  test('can rename a category and see updated name in the list', async ({ page }) => {
    const catName = `E2E Rename Cat ${Date.now()}`;
    const newName = `Renamed Cat ${Date.now()}`;

    // Create category via the UI form
    await page.getByRole('button', { name: /Categories/ }).click();
    await page.getByPlaceholder('Category name').fill(catName);
    await page.getByRole('button', { name: 'Add Category' }).click();
    await expect(page.getByText(catName)).toBeVisible({ timeout: 5_000 });

    // Open edit dialog
    const catRow = page.locator('tr').filter({ hasText: catName });
    await catRow.locator('button[title="Edit category"]').click();
    const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Edit Category' });
    await expect(dialog).toBeVisible();

    // Change name and save
    await dialog.locator('#cat-edit-name').fill(newName);
    await dialog.getByRole('button', { name: 'Save' }).click();

    // Success toast
    await expect(page.getByText('Category updated')).toBeVisible({ timeout: 5_000 });

    // Updated name appears in the table
    await expect(page.locator('tr').filter({ hasText: newName })).toBeVisible({ timeout: 5_000 });
    // Old name is gone
    await expect(page.locator('tr').filter({ hasText: catName })).not.toBeVisible();
  });
});
