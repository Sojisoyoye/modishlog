import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { ensureProduct, addStock, createSale, voidSale } from './helpers/data';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/reports');
  await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
});

test('shows Reports heading and three report cards', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
  await expect(page.getByText('Profit & Loss')).toBeVisible();
  await expect(page.getByText('Stock Report')).toBeVisible();
  await expect(page.getByText('Purchase & Sale')).toBeVisible();
});

test('navigates to profit/loss report page', async ({ page }) => {
  await page.getByText('Profit & Loss').click();
  await expect(page).toHaveURL('/reports/profit-loss');
  await expect(page.getByRole('heading', { name: 'Profit & Loss Report' })).toBeVisible();
});

test('navigates to stock report page', async ({ page }) => {
  await page.getByText('Stock Report').click();
  await expect(page).toHaveURL('/reports/stock');
  await expect(page.getByRole('heading', { name: 'Stock Report' })).toBeVisible();
});

test('navigates to purchase & sale report page', async ({ page }) => {
  await page.getByText('Purchase & Sale').click();
  await expect(page).toHaveURL('/reports/purchase-sale');
  await expect(page.getByRole('heading', { name: 'Purchase & Sale Report' })).toBeVisible();
});

test('profit/loss page has date filters and generate button', async ({ page }) => {
  await page.goto('/reports/profit-loss');
  await expect(page.locator('input[type="date"]').first()).toBeVisible();
  await expect(page.locator('input[type="date"]').nth(1)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Generate Report' })).toBeVisible();
});

test('stock report page has generate button', async ({ page }) => {
  await page.goto('/reports/stock');
  await expect(page.getByRole('button', { name: 'Generate Report' })).toBeVisible();
});

test.describe('P&L report generation', () => {
  let saleId: string;
  // Shared dates computed once to avoid midnight edge cases across beforeAll and test
  const today = new Date().toISOString().split('T')[0];
  const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

  test.beforeAll(async () => {
    const product = await ensureProduct('E2E Reports Product');
    await addStock(product.id, 10);
    const sale = await createSale(product.id, { quantity: 1, unitPrice: '9000.00', saleDate: today });
    saleId = sale.id;
  });

  test.afterAll(async () => {
    if (saleId) await voidSale(saleId).catch((e: Error) => {
      if (!/4\d\d/.test(e.message)) throw e;
    });
  });

  test('P&L report generates with Net Profit and Total Sales figures', async ({ page }) => {
    await page.goto('/reports/profit-loss');
    await expect(page.getByRole('heading', { name: 'Profit & Loss Report' })).toBeVisible();

    await page.locator('input[type="date"]').first().fill(thirtyDaysAgo);
    await page.locator('input[type="date"]').nth(1).fill(today);
    await page.getByRole('button', { name: 'Generate Report' }).click();
    await page.waitForLoadState('networkidle');

    // Net Profit section: prominent 4xl value formatted by number:'1.2-2'
    await expect(page.getByText('Net Profit', { exact: true })).toBeVisible();
    // Allow surrounding whitespace from Angular template interpolation
    await expect(page.locator('p.text-4xl.font-bold').first()).toHaveText(/-?\d[\d,.]*\.\d{2}/);

    // Total Sales card: seeded sale guarantees a non-zero value
    await expect(page.getByText('Total Sales')).toBeVisible();
    // Target the specific summary card div using its rounded-xl class (not the outer grid wrapper)
    const totalSalesCard = page.locator('div.rounded-xl').filter({
      has: page.locator('p', { hasText: 'Total Sales' })
    }).first();
    await expect(totalSalesCard.locator('p.text-xl.font-bold')).toHaveText(/\d[\d,.]*\.\d{2}/);
  });
});

test.describe('Stock report generation', () => {
  test.beforeAll(async () => {
    // Ensure at least one product with stock exists independently of other describes
    const product = await ensureProduct('E2E Reports Product');
    await addStock(product.id, 5);
  });

  test('Stock report generates and shows at least one product row', async ({ page }) => {
    await page.goto('/reports/stock');
    await expect(page.getByRole('heading', { name: 'Stock Report' })).toBeVisible();

    await page.getByRole('button', { name: 'Generate Report' }).click();
    await page.waitForLoadState('networkidle');

    // Results table must be visible with at least one product row
    await expect(page.locator('table tbody tr').first()).toBeVisible();

    // Total stock value renders as a formatted decimal
    await expect(page.locator('p.text-2xl.font-bold').first()).toHaveText(/\d[\d,]*\.\d{2}/);
  });
});

test.describe('Reports auto-load on page open', () => {
  test.beforeAll(async () => {
    const product = await ensureProduct('Auto-load Test Product');
    await addStock(product.id, 5);
  });

  test('profit/loss page auto-loads report without user interaction', async ({ page }) => {
    await page.goto('/reports/profit-loss');
    await expect(page.getByRole('heading', { name: 'Profit & Loss Report' })).toBeVisible();
    await expect(page.getByText('Net Profit', { exact: true })).toBeVisible({ timeout: 10000 });
    await expect(page.locator('p.text-4xl.font-bold').first()).toBeVisible();
  });

  test('profit/loss date pickers are pre-filled on page open', async ({ page }) => {
    await page.goto('/reports/profit-loss');
    await expect(page.locator('#pl-start-date')).not.toHaveValue('', { timeout: 5000 });
    await expect(page.locator('#pl-end-date')).not.toHaveValue('');
  });

  test('purchase-sale page auto-loads report without user interaction', async ({ page }) => {
    await page.goto('/reports/purchase-sale');
    await expect(page.getByRole('heading', { name: 'Purchase & Sale Report' })).toBeVisible();
    await expect(page.getByText('Net Position', { exact: true })).toBeVisible({ timeout: 10000 });
  });

  test('purchase-sale date pickers are pre-filled on page open', async ({ page }) => {
    await page.goto('/reports/purchase-sale');
    await expect(page.locator('#ps-start-date')).not.toHaveValue('', { timeout: 5000 });
    await expect(page.locator('#ps-end-date')).not.toHaveValue('');
  });

  test('stock report page auto-loads table without user interaction', async ({ page }) => {
    await page.goto('/reports/stock');
    await expect(page.getByRole('heading', { name: 'Stock Report' })).toBeVisible();
    await expect(page.locator('table').first()).toBeVisible({ timeout: 10000 });
  });
});
