import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';
import { ensureProduct } from './helpers/data';

const API = 'http://localhost:8000/api/v1';

async function createStockCount(countType: 'PRODUCT' | 'LOT', notes?: string) {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const today = new Date().toISOString().split('T')[0];
    const resp = await ctx.post(`${API}/stockcount/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { count_date: today, count_type: countType, notes: notes ?? null },
    });
    if (!resp.ok()) throw new Error(`Create stock count failed: ${resp.status()} ${await resp.text()}`);
    return resp.json();
  } finally {
    await ctx.dispose();
  }
}

async function finalizeStockCount(id: string) {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.post(`${API}/stockcount/${id}/finalize`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok()) throw new Error(`Finalize failed: ${resp.status()} ${await resp.text()}`);
    return resp.json();
  } finally {
    await ctx.dispose();
  }
}

test.describe('Stock count feature', () => {
  test.beforeAll(async () => {
    await ensureTestUser();
    await ensureProduct('Stock Count E2E Product');
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('stock counts page is accessible from nav', async ({ page }) => {
    await page.goto('/stock-counts');
    await expect(page.getByRole('heading', { name: /Stock Counts/i })).toBeVisible();
  });

  test('create a PRODUCT-type stock count and see it in the list', async ({ page }) => {
    await page.goto('/stock-counts');
    await page.getByRole('button', { name: /New Stock Count/i }).click();

    // Creation dialog
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByLabel(/Count date/i).fill(new Date().toISOString().split('T')[0]);
    await dialog.getByRole('radio', { name: /Product/i }).check();
    await dialog.getByRole('button', { name: /Create/i }).click();

    // Should navigate to the detail page
    await page.waitForURL(/\/stock-counts\/.+/);
    await expect(page.getByText('DRAFT')).toBeVisible();
    await expect(page.getByText('PRODUCT')).toBeVisible();
  });

  test('detail page shows items with no system quantity until finalized', async ({ page }) => {
    const sc = await createStockCount('PRODUCT');
    await page.goto(`/stock-counts/${sc.id}`);

    await expect(page.getByText('DRAFT')).toBeVisible();
    // System qty column should show — (null/unfinalized)
    const systemCells = page.locator('td').filter({ hasText: /^—$/ });
    await expect(systemCells.first()).toBeVisible();
  });

  test('finalise a stock count and verify inputs become read-only', async ({ page }) => {
    const sc = await createStockCount('PRODUCT', 'E2E finalize test');
    await page.goto(`/stock-counts/${sc.id}`);

    await page.getByRole('button', { name: /Finalise/i }).click();

    // Confirm dialog
    const confirmDialog = page.getByRole('dialog').filter({ hasText: /Finalise/ });
    await confirmDialog.getByRole('button', { name: /Confirm/i }).click();

    await expect(page.getByText('FINALIZED')).toBeVisible();
    // Counted qty inputs should be gone (read-only after finalization)
    await expect(page.getByRole('spinbutton')).toHaveCount(0);
  });

  test('finalised count appears in the stock counts list', async ({ page }) => {
    const sc = await createStockCount('PRODUCT', 'E2E list test');
    await finalizeStockCount(sc.id);

    await page.goto('/stock-counts');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('table tbody tr').filter({ hasText: 'FINALIZED' }).first()).toBeVisible();
  });
});
