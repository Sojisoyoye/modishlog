import { test, expect } from '@playwright/test';
import { loginViaAPI, ensureTestUser } from './helpers/auth';
import { ensureProduct, createSale, voidSale, advanceOrderToStatus, createOrder } from './helpers/data';

test.describe.configure({ mode: 'serial' });

let productId: string;
let saleId: string;
let orderId: string;

test.beforeAll(async () => {
  await ensureTestUser();

  // Seed: product → delivered order (sets stock + FIFO cost) → sale (drives portfolio margin)
  const product = await ensureProduct('E2E Pricing Product');
  productId = product.id;

  // Delivered order adds stock so createSale can consume it
  const order = await createOrder(productId, { currency: 'NGN', quantity: 10, unitCost: '3000.00' });
  orderId = order.id;
  await advanceOrderToStatus(orderId, 'DELIVERED', { fxRateAtDelivery: '1500' });

  // Sale within the last 30 days drives blended_margin calculation
  const sale = await createSale(productId, { quantity: 2, unitPrice: '5000.00' });
  saleId = sale.id;
});

test.afterAll(async () => {
  await voidSale(saleId).catch(() => {});
  // DELIVERED orders cannot be cancelled (terminal status) — skip deleteOrder
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

    // Locate the blended margin value by its sibling label text to avoid matching other large numbers
    const marginCard = page.locator('p').filter({ hasText: /\d+\.\d+%/ }).first();
    await expect(marginCard).toBeVisible({ timeout: 10_000 });

    const marginText = await marginCard.textContent();
    expect(marginText).toMatch(/\d+\.\d+%/);

    // Confirm it's not 0.0% — requires the seeded sale data
    const marginValue = parseFloat((marginText ?? '').replace('%', '').trim());
    expect(marginValue).toBeGreaterThan(0);
  });

  test('per-product margin table has at least one row with a product name', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });

    await expect(page.getByRole('heading', { name: 'Per-Product Margins' })).toBeVisible();

    // Table body should have at least one data row (not the colspan empty-state row)
    const tableRows = page.locator('table tbody tr').filter({
      hasNot: page.locator('td[colspan]'),
    });
    await expect(tableRows.first()).toBeVisible({ timeout: 10_000 });

    // Product name cell should contain text
    const firstProductCell = tableRows.first().locator('td').first();
    const productName = await firstProductCell.textContent();
    expect(productName?.trim().length).toBeGreaterThan(0);
  });

  test('Demand Elasticity section is present and has a populated product selector', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });

    await expect(page.getByRole('heading', { name: 'Demand Elasticity' })).toBeVisible();

    const productSelect = page.locator('#pricing-elasticity-product');
    await expect(productSelect).toBeVisible();

    // Dropdown must have more than the placeholder "Select product..." option
    const optionCount = await productSelect.locator('option').count();
    expect(optionCount).toBeGreaterThan(1);
  });

  test('elasticity coefficient can be saved and appears in the table', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });

    const productSelect = page.locator('#pricing-elasticity-product');
    await productSelect.selectOption({ label: 'E2E Pricing Product' });

    const coeffInput = page.locator('#pricing-elasticity-coeff');
    await coeffInput.fill('-1.5');
    await page.getByRole('button', { name: /save/i }).click();

    await expect(page.locator('.p-toast')).toContainText('Saved', { timeout: 10_000 });

    // Scope the elasticity table via its section heading to avoid nth(1) fragility
    const elasticitySection = page
      .locator('div')
      .filter({ has: page.getByRole('heading', { name: 'Demand Elasticity' }) })
      .last();
    const elasticityTable = elasticitySection.locator('table');
    await expect(elasticityTable.locator('tbody tr').first()).toBeVisible({ timeout: 10_000 });
    await expect(elasticityTable).toContainText('E2E Pricing Product');
    await expect(elasticityTable).toContainText('-1.50');
  });
});
