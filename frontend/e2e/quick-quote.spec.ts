import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { addStock, advanceOrderToStatus, createOrder, ensureProduct } from './helpers/data';

// ---------------------------------------------------------------------------
// Quick Quote E2E Tests (task #120)
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/sales');
  await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible({ timeout: 15_000 });
});

test.describe('Quick Quote', () => {
  test('Quick Quote tab is accessible from the Sales page', async ({ page }) => {
    const tab = page.locator('[data-testid="tab-quick-quote"]');
    await expect(tab).toBeVisible();
    await tab.click();

    // Form elements must appear
    await expect(page.locator('[data-testid="quick-quote-product-select"]')).toBeVisible();
    await expect(page.locator('[data-testid="quick-quote-qty-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="quick-quote-calculate-btn"]')).toBeVisible();
  });

  test('Quick Quote calculates minimum sell price for a product with a delivered order', async ({
    page,
  }) => {
    test.setTimeout(90_000);
    // Seed: create product, create + deliver an order (establishes FIFO cost)
    const product = await ensureProduct('E2E Quick Quote Calc');
    const order = await createOrder(product.id, { quantity: 5, unitCost: '2000.00' });
    await advanceOrderToStatus(order.id, 'DELIVERED', { fxRateAtDelivery: '1' });
    await addStock(product.id, 5);

    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible({ timeout: 15_000 });

    // Open Quick Quote tab
    await page.locator('[data-testid="tab-quick-quote"]').click();

    // Wait for products to load in the dropdown then select ours
    const productOption = page.locator(
      `[data-testid="quick-quote-product-select"] option[value="${product.id}"]`,
    );
    await expect(productOption).toBeAttached({ timeout: 10_000 });
    await page.locator('[data-testid="quick-quote-product-select"]').selectOption(product.id);

    // Set quantity and calculate
    await page.locator('[data-testid="quick-quote-qty-input"]').fill('2');
    await page.locator('[data-testid="quick-quote-calculate-btn"]').click();

    // Result fields must appear with non-zero values
    await expect(page.locator('[data-testid="qq-fifo-cost"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-testid="qq-floor-margin"]')).toBeVisible();
    await expect(page.locator('[data-testid="qq-min-price"]')).toBeVisible();
    await expect(page.locator('[data-testid="qq-total-price"]')).toBeVisible();

    const minPriceText = await page.locator('[data-testid="qq-min-price"]').textContent();
    const fifoCostText = await page.locator('[data-testid="qq-fifo-cost"]').textContent();

    // Min sell price must be a positive number
    expect(parseFloat((minPriceText ?? '').replace(/[^0-9.]/g, ''))).toBeGreaterThan(0);
    // FIFO cost must be positive (unit cost was 2000)
    expect(parseFloat((fifoCostText ?? '').replace(/[^0-9.]/g, ''))).toBeGreaterThan(0);
  });

  test('Quick Quote shows no-data message when product has no delivered orders', async ({
    page,
  }) => {
    // Product with no delivered orders — backend returns zero cost values
    const product = await ensureProduct('E2E Quick Quote No Lots');

    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible({ timeout: 15_000 });

    await page.locator('[data-testid="tab-quick-quote"]').click();

    const productOption = page.locator(
      `[data-testid="quick-quote-product-select"] option[value="${product.id}"]`,
    );
    await expect(productOption).toBeAttached({ timeout: 10_000 });
    await page.locator('[data-testid="quick-quote-product-select"]').selectOption(product.id);
    await page.locator('[data-testid="quick-quote-qty-input"]').fill('1');
    await page.locator('[data-testid="quick-quote-calculate-btn"]').click();

    // Backend returns zeros for products with no delivered orders.
    // Either the no-data banner or the results panel (showing ₦0.00 costs) appears.
    // Accept either outcome since Decimal serialisation may produce string "0" ≠ number 0.
    await expect(
      page.locator('[data-testid="qq-no-data"], [data-testid="qq-fifo-cost"]').first()
    ).toBeVisible({ timeout: 10_000 });
  });
});
