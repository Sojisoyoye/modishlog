import { test, expect, request } from '@playwright/test';
import { loginViaAPI, getAPIToken } from './helpers/auth';
import { ensureProduct, addStock, createSale, voidSale, advanceOrderToStatus, createOrder, deleteOrder } from './helpers/data';

test.describe.configure({ mode: 'serial' });

const API = 'http://localhost:8000/api/v1';

let productId: string;
let saleId: string;
let orderId: string;

test.beforeAll(async () => {
  // Seed: product → delivered order (sets unit_cost) → sale (drives portfolio margin)
  const product = await ensureProduct('E2E Pricing Product');
  productId = product.id;

  // Delivered order so inventory + cost price are set
  const order = await createOrder(productId, { currency: 'NGN', quantity: 10, unitCost: '3000.00' });
  orderId = order.id;
  await advanceOrderToStatus(orderId, 'DELIVERED', { fxRateAtDelivery: '1' });

  // Sale within the last 30 days — drives blended_margin calculation
  const sale = await createSale(productId, { quantity: 2, unitPrice: '5000.00' });
  saleId = sale.id;
});

test.afterAll(async () => {
  await voidSale(saleId).catch(() => {});
  await deleteOrder(orderId).catch(() => {});
});

test.describe('Pricing & Margins page', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaAPI(page);
  });

  test('page loads with correct heading', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText('404')).not.toBeVisible();
    await expect(page.getByText('Error')).not.toBeVisible();
  });

  test('Blended Portfolio Margin card shows a numeric % value', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });

    // The blended margin is rendered as "X.X%" — assert it is not empty or zero
    const marginCard = page.locator('p.text-4xl');
    await expect(marginCard).toBeVisible();

    const marginText = await marginCard.textContent();
    expect(marginText).toMatch(/\d+\.\d+%/);

    // Confirm it's not 0.0% (requires seeded sale data)
    const marginValue = parseFloat((marginText ?? '').replace('%', '').trim());
    expect(marginValue).toBeGreaterThan(0);
  });

  test('per-product margin table has at least one row with a product name', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });

    // Wait for the Per-Product Margins section heading
    await expect(page.getByRole('heading', { name: 'Per-Product Margins' })).toBeVisible();

    // Table body should have at least one data row (not the empty-state row)
    const tableRows = page.locator('table tbody tr').filter({
      hasNot: page.locator('td[colspan]'),
    });
    await expect(tableRows.first()).toBeVisible({ timeout: 10_000 });

    // Product name cell in the first data row should contain text
    const firstProductCell = tableRows.first().locator('td').first();
    const productName = await firstProductCell.textContent();
    expect(productName?.trim().length).toBeGreaterThan(0);
  });

  test('Demand Elasticity section is present and has a product selector', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });

    await expect(page.getByRole('heading', { name: 'Demand Elasticity' })).toBeVisible();

    // Product select dropdown should be visible and populated
    const productSelect = page.locator('#pricing-elasticity-product');
    await expect(productSelect).toBeVisible();

    // After products load, the dropdown should have at least one option beyond "Select product..."
    await expect(productSelect.locator('option')).toHaveCount(
      await productSelect.locator('option').count(),
    );
    const optionCount = await productSelect.locator('option').count();
    expect(optionCount).toBeGreaterThan(1);
  });

  test('elasticity coefficient can be saved and appears in the table', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });

    // Select the seeded product in the elasticity dropdown
    const productSelect = page.locator('#pricing-elasticity-product');
    await productSelect.selectOption({ label: 'E2E Pricing Product' });

    // Enter a coefficient and save
    const coeffInput = page.locator('#pricing-elasticity-coeff');
    await coeffInput.fill('-1.5');
    await page.getByRole('button', { name: /save/i }).click();

    // Toast should confirm success
    await expect(page.locator('.p-toast')).toContainText('Saved', { timeout: 10_000 });

    // Elasticity table should now show the product row
    const elasticityTable = page.locator('table').nth(1);
    await expect(elasticityTable.locator('tbody tr').first()).toBeVisible({ timeout: 10_000 });
    await expect(elasticityTable).toContainText('E2E Pricing Product');
    await expect(elasticityTable).toContainText('-1.50');
  });
});
