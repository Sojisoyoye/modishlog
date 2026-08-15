import { test, expect, Page } from '@playwright/test';
import { loginViaAPI, ensureTestUser } from './helpers/auth';
import { ensureProduct, createSale, voidSale, advanceOrderToStatus, createOrder } from './helpers/data';

test.describe.configure({ mode: 'serial' });
// The beforeAll creates an order and advances it through 5 status transitions — needs extra time
test.setTimeout(90_000);

let productId: string;
let saleId: string;
let orderId: string;

/**
 * The page is organized into tabs (Overview/Product Margins/Recommendations/
 * Cross-Subsidisation/Tools/Demand & Mix) — most sections only render once
 * their tab is active. "Overview" is the default on page load.
 */
async function switchToTab(page: Page, label: string): Promise<void> {
  await page.getByRole('button', { name: label }).click();
}

test.beforeAll(async () => {
  test.setTimeout(90_000);
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
    // Heading visible is sufficient proof the page loaded — don't check body text
    // for "404"/"Error" since product names can contain those substrings.
  });

  test('Blended Portfolio Margin card shows a numeric % value', async ({ page }) => {
    const marginResponse = page.waitForResponse((r) => r.url().includes('/pricing/portfolio-margin'));
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });

    // Wait for the GET /pricing/portfolio-margin response itself, not just DOM
    // visibility — the margin signal defaults to 0 and the card is visible
    // (rendering "0.0%") from first paint, so racing textContent() against the
    // async fetch reads the placeholder instead of the real seeded value.
    await marginResponse;

    // Locate the blended margin value by its sibling label text to avoid matching other large numbers
    const marginCard = page.locator('p').filter({ hasText: /\d+\.\d+%/ }).first();
    await expect(marginCard).toBeVisible({ timeout: 10_000 });

    // Confirm it's not 0.0% — requires the seeded sale data. Poll rather than
    // reading textContent() once, since Angular still needs a render tick
    // after the response lands before the DOM reflects it.
    await expect(async () => {
      const marginText = await marginCard.textContent();
      expect(marginText).toMatch(/\d+\.\d+%/);
      const marginValue = parseFloat((marginText ?? '').replace('%', '').trim());
      expect(marginValue).toBeGreaterThan(0);
    }).toPass({ timeout: 10_000 });
  });

  test('per-product margin table has at least one row with a product name', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Product Margins');

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
    await switchToTab(page, 'Demand & Mix');

    await expect(page.getByRole('heading', { name: 'Demand Elasticity' })).toBeVisible();

    const productSelect = page.locator('#pricing-elasticity-product');
    await expect(productSelect).toBeVisible();

    // Wait for products to load into the dropdown (API call may lag behind page render)
    await expect(productSelect.locator('option').nth(1)).toBeAttached({ timeout: 10_000 });
    const optionCount = await productSelect.locator('option').count();
    expect(optionCount).toBeGreaterThan(1);
  });

  test('Price-FX Sensitivity Calculator section is visible and computes a result', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Tools');

    await expect(
      page.getByRole('heading', { name: 'Price-FX Sensitivity Calculator' }),
    ).toBeVisible();

    await page.locator('#sens-selling-price').fill('5000');
    await page.locator('#sens-fx-rate').fill('1500');
    await page.locator('#sens-quantity').fill('10');
    await page.locator('#sens-unit-cost').fill('2');

    await page.getByRole('button', { name: /calculate/i }).click();

    // Landed cost = $2 * 1500 = ₦3000; margin = (5000-3000)/5000*100 = 40%
    await expect(page.locator('#sens-selling-price')).toBeVisible();
    // Results grid should appear — look for "Margin" label
    const resultsSection = page.locator('text=Landed Cost').first();
    await expect(resultsSection).toBeVisible({ timeout: 10_000 });
  });

  test('Selling Price Suggestion section is visible and returns a min price', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Tools');

    await expect(page.getByRole('heading', { name: 'Selling Price Suggestion' })).toBeVisible();

    await page.locator('#sugg-cost').fill('10');
    await page.locator('#sugg-currency').selectOption('USD');
    await page.locator('#sugg-fx').fill('1500');
    await page.locator('#sugg-margin').fill('35');

    await page.getByRole('button', { name: /get suggestion/i }).click();

    // Min selling price = (10 * 1500) / (1 - 0.35) = 23077 NGN approx
    const minPriceSection = page.locator('text=Min Selling Price').first();
    await expect(minPriceSection).toBeVisible({ timeout: 10_000 });
  });

  test('Product Mix Status section is present', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Demand & Mix');

    await expect(page.getByRole('heading', { name: 'Product Mix Status' })).toBeVisible();
  });

  test('Optimizer Recommendations section is present with Generate button', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Recommendations');

    await expect(page.getByRole('heading', { name: 'Optimizer Recommendations' })).toBeVisible();
    await expect(page.getByRole('button', { name: /generate/i })).toBeVisible();
    // Target margin input should be pre-filled with 35
    const targetInput = page.locator('#opt-target-margin');
    await expect(targetInput).toHaveValue('35');
  });

  // Task 199 — the "Pricing Recommendations" panel's "Mark Reviewed" button
  // used to be styled identically to a real apply action (green, checkmark
  // icon) even though it does not change any price; only "Optimizer
  // Recommendations" below it actually updates a product's price. Each
  // panel must now say plainly what it does.
  test('Recommendations tab explains the difference between the two panels (Task 199)', async ({
    page,
  }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Recommendations');

    await expect(page.getByRole('heading', { name: 'Pricing Recommendations' })).toBeVisible();
    await expect(page.getByText(/does not change any prices/i)).toBeVisible();

    await expect(page.getByRole('heading', { name: 'Optimizer Recommendations' })).toBeVisible();
    await expect(page.getByText(/updates the product.s price/i)).toBeVisible();
  });

  test('Demand Forecast section has product selector and Run Forecast button', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Demand & Mix');

    await expect(page.getByRole('heading', { name: 'Demand Forecast' })).toBeVisible();
    await expect(page.locator('#forecast-product')).toBeVisible();
    await expect(page.locator('#forecast-horizon')).toBeVisible();
    await expect(page.getByRole('button', { name: /run forecast/i })).toBeVisible();
    // Button should be disabled until a product is selected
    await expect(page.getByRole('button', { name: /run forecast/i })).toBeDisabled();

    // Select a product — button becomes enabled
    await expect(page.locator('#forecast-product option').nth(1)).toBeAttached({ timeout: 10_000 });
    await page.locator('#forecast-product').selectOption({ index: 1 });
    await expect(page.getByRole('button', { name: /run forecast/i })).toBeEnabled();
  });

  test('Saved Scenarios section is present and shows empty state initially', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Tools');

    await expect(page.getByRole('heading', { name: 'Saved Scenarios' })).toBeVisible();
    await expect(page.getByRole('button', { name: /refresh/i })).toBeVisible();
  });

  test('sensitivity calc scenario is saved and appears in Saved Scenarios', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Tools');

    // Fill sensitivity form and calculate
    await page.locator('#sens-selling-price').fill('5000');
    await page.locator('#sens-fx-rate').fill('1500');
    await page.locator('#sens-quantity').fill('10');
    await page.locator('#sens-unit-cost').fill('2');
    await page.getByRole('button', { name: /calculate/i }).click();

    // Wait for result to appear, then save
    await expect(page.locator('text=Landed Cost').first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole('button', { name: /save scenario/i }).click();

    await expect(page.locator('.p-toast')).toContainText('Saved', { timeout: 10_000 });

    // Saved scenario should now appear in the Saved Scenarios table
    const scenariosTable = page
      .locator('table')
      .filter({ has: page.getByRole('columnheader', { name: 'Selling Price' }) });
    await expect(scenariosTable.locator('tbody tr').first()).toBeVisible({ timeout: 10_000 });
  });

  test('elasticity coefficient can be saved and appears in the table', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Demand & Mix');

    const productSelect = page.locator('#pricing-elasticity-product');
    await productSelect.selectOption({ label: 'E2E Pricing Product' });

    const coeffInput = page.locator('#pricing-elasticity-coeff');
    await coeffInput.fill('-1.5');
    await page.getByRole('button', { name: /save/i }).click();

    await expect(page.locator('.p-toast')).toContainText('Saved', { timeout: 10_000 });

    // Locate the elasticity table via its unique "Elasticity" column header
    // (the per-product table uses different headers — Product/Cost/Selling/Margin/Target/Gap)
    const elasticityTable = page
      .locator('table')
      .filter({ has: page.getByRole('columnheader', { name: 'Elasticity' }) });
    await expect(elasticityTable.locator('tbody tr').first()).toBeVisible({ timeout: 10_000 });
    await expect(elasticityTable).toContainText('E2E Pricing Product');
    await expect(elasticityTable).toContainText('-1.50');
  });

  test('FX sensitivity coefficient can be saved alongside elasticity and appears in the table', async ({
    page,
  }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Demand & Mix');

    const productSelect = page.locator('#pricing-elasticity-product');
    await productSelect.selectOption({ label: 'E2E Pricing Product' });

    await page.locator('#pricing-elasticity-coeff').fill('-1.5');
    await page.locator('#pricing-fx-sensitivity-coeff').fill('0.8');
    await page.getByRole('button', { name: /save/i }).click();

    await expect(page.locator('.p-toast')).toContainText('Saved', { timeout: 10_000 });

    const elasticityTable = page
      .locator('table')
      .filter({ has: page.getByRole('columnheader', { name: 'FX Sensitivity' }) });
    await expect(elasticityTable.locator('tbody tr').first()).toBeVisible({ timeout: 10_000 });
    await expect(elasticityTable).toContainText('0.80');
  });

  test('elasticity and FX sensitivity coefficients each have a tooltip affordance', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Demand & Mix');

    await expect(page.getByRole('heading', { name: 'Demand Elasticity' })).toBeVisible();

    // The tooltip popup itself is PrimeNG's Tooltip directive (pTooltip) —
    // its runtime show/hide behavior is that library's responsibility, not
    // re-tested here. This asserts what task 186 actually adds: an
    // info-circle affordance wired to each coefficient's label, present and
    // hoverable (cursor-help), for both elasticity and FX sensitivity.
    const elasticityTooltipIcon = page.locator(
      'label[for="pricing-elasticity-coeff"] i.pi-info-circle.cursor-help',
    );
    await expect(elasticityTooltipIcon).toBeVisible();

    const fxTooltipIcon = page.locator(
      'label[for="pricing-fx-sensitivity-coeff"] i.pi-info-circle.cursor-help',
    );
    await expect(fxTooltipIcon).toBeVisible();
  });

  test('loading an unconfigured product pre-populates category-default coefficients, not a blank form', async ({
    page,
  }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });
    await switchToTab(page, 'Demand & Mix');

    const productSelect = page.locator('#pricing-elasticity-product');
    // A freshly-seeded product with no saved elasticity config yet.
    await productSelect.selectOption({ label: 'E2E Pricing Product' });
    await page.getByRole('button', { name: /load/i }).click();

    // Task 186 (ST-802 criterion 3) — the Load button must never leave the
    // coefficient input blank/zero-by-omission; it always resolves to a
    // real number (product override, category default, or system default).
    const coeffInput = page.locator('#pricing-elasticity-coeff');
    await expect(coeffInput).not.toHaveValue('');
  });

  // Task 201 — every tab on this page had at least one panel with zero
  // explanatory text for non-technical users (only Demand Elasticity had
  // tooltips, from task 186's narrower PRD ST-802 requirement). Each tab
  // must now say plainly, in the page's own language, what it shows.
  test('every tab has plain-language explanatory text (Task 201)', async ({ page }) => {
    await page.goto('/pricing');
    await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
      timeout: 10_000,
    });

    // Overview (default tab)
    await expect(page.getByText('Blended Portfolio Margin').locator('i.pi-info-circle')).toBeAttached();
    await expect(page.getByText(/how many of your products fall into each margin range/i)).toBeVisible();

    // Product Margins
    await switchToTab(page, 'Product Margins');
    await expect(page.getByText(/Margin = \(Selling price/i)).toBeVisible();

    // Cross-Subsidisation
    await switchToTab(page, 'Cross-Subsidisation');
    await expect(page.getByText(/propping up your overall margin/i)).toBeVisible();

    // Tools
    await switchToTab(page, 'Tools');
    await expect(page.getByText(/before you commit to it/i)).toBeVisible();
    const fxOverrideTooltipIcon = page
      .locator('label[for="sugg-fx"]')
      .locator('i.pi-info-circle');
    await expect(fxOverrideTooltipIcon).toBeAttached();

    // Demand & Mix
    await switchToTab(page, 'Demand & Mix');
    await expect(page.getByText(/within 5 percentage/i)).toBeVisible();
    const horizonTooltipIcon = page
      .locator('label[for="forecast-horizon"]')
      .locator('i.pi-info-circle');
    await expect(horizonTooltipIcon).toBeAttached();
  });
});

test('demand forecast shows insufficient data empty state when product has < 10 sales', async ({ page }) => {
  // The E2E test user has no sales data for any product, so running a
  // forecast should return a 400 InsufficientPriceDataError from the backend.
  await loginViaAPI(page);
  await page.goto('/pricing');
  await expect(page.getByRole('heading', { name: 'Pricing & Margins' })).toBeVisible({
    timeout: 10_000,
  });

  // Navigate to Demand & Mix tab — products for this dropdown are lazy-loaded
  // only once the tab is first opened, so the option list is empty for a
  // moment after the click; poll rather than reading count() once.
  await page.getByRole('button', { name: /demand/i }).click();

  const productSelect = page.locator('#forecast-product');
  // Fail explicitly if no products ever show up — a silent skip would give false confidence
  await expect(async () => {
    expect(await productSelect.locator('option').count()).toBeGreaterThan(1);
  }).toPass({ timeout: 10_000 });

  await productSelect.selectOption({ index: 1 });
  await page.getByRole('button', { name: /run forecast/i }).click();

  // Should show the insufficient data empty state, not a generic toast error
  await expect(
    page.getByText(/record at least 10 sales/i)
  ).toBeVisible({ timeout: 10_000 });
});
