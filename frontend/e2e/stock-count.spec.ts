import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';
import { ensureProduct, createOrder, advanceOrderToStatus } from './helpers/data';

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

async function getStockCount(id: string) {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.get(`${API}/stockcount/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok()) throw new Error(`Get stock count failed: ${resp.status()} ${await resp.text()}`);
    return resp.json();
  } finally {
    await ctx.dispose();
  }
}

async function updateStockCountItem(countId: string, itemId: string, countedQty: number) {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.patch(`${API}/stockcount/${countId}/items/${itemId}`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { counted_quantity: countedQty },
    });
    if (!resp.ok()) throw new Error(`Update item failed: ${resp.status()} ${await resp.text()}`);
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
    await expect(page.getByText('PRODUCT').first()).toBeVisible();
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

// ---------------------------------------------------------------------------
// LOT-type stock count tests
// ---------------------------------------------------------------------------

test.describe('LOT-type stock count', () => {
  test.describe.configure({ mode: 'serial' });

  let lotCountId: string;

  test.beforeAll(async () => {
    await ensureTestUser();
    // Deliver an order so OrderLineItem.units_remaining > 0 → LOT items appear
    const product = await ensureProduct('E2E LOT Count Product');
    const order = await createOrder(product.id, { currency: 'NGN', quantity: 10, unitCost: '3000.00' });
    await advanceOrderToStatus(order.id, 'DELIVERED', { fxRateAtDelivery: '1500' });

    // Pre-create a LOT count for variance and finalization tests
    const sc = await createStockCount('LOT', 'E2E LOT variance test');
    lotCountId = sc.id;
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('create LOT-type stock count via UI and see lot rows', async ({ page }) => {
    await page.goto('/stock-counts');
    await page.getByRole('button', { name: /New Stock Count/i }).click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByLabel(/Count date/i).fill(new Date().toISOString().split('T')[0]);
    await dialog.getByRole('radio', { name: /Lot level/i }).check();
    await dialog.getByRole('button', { name: /Create/i }).click();

    // Should navigate to the LOT-type detail page
    await page.waitForURL(/\/stock-counts\/.+/);
    await expect(page.getByText('DRAFT')).toBeVisible();

    // LOT-type shows the extra "Lot (Order line)" column header
    await expect(page.getByText('Lot (Order line)')).toBeVisible();

    // At least one data row (not the empty-state colspan row)
    const dataRows = page.locator('table tbody tr').filter({
      hasNot: page.locator('td[colspan]'),
    });
    await expect(dataRows.first()).toBeVisible({ timeout: 10_000 });
  });

  test('enter counted quantity and view variance after finalization', async ({ page }) => {
    // Get the first item ID from the pre-created LOT count
    const sc = await getStockCount(lotCountId);
    const firstItem = sc.items[0];
    if (!firstItem) throw new Error(`LOT count ${lotCountId} has no items — delivery may not have completed`);

    // Set counted_quantity to 0 via API (will produce a negative variance when system_qty is snapshotted)
    await updateStockCountItem(lotCountId, firstItem.id, 0);

    await page.goto(`/stock-counts/${lotCountId}`);
    await expect(page.getByText('DRAFT')).toBeVisible();

    // Counted qty input for the first row should show 0 (or empty, which renders as 0)
    const countedInput = page.getByRole('spinbutton').first();
    await expect(countedInput).toBeVisible();
    const inputVal = await countedInput.inputValue();
    // The input shows '0', '0.000000', or '' depending on how the backend returns the value
    expect(['0', '0.000000', '']).toContain(inputVal);

    // Finalize: snapshot system_qty and lock the count
    await page.getByRole('button', { name: /Finalise/i }).click();
    const confirmDialog = page.getByRole('dialog').filter({ hasText: /Finalise/ });
    await confirmDialog.getByRole('button', { name: /Confirm/i }).click();

    await expect(page.getByText('FINALIZED')).toBeVisible({ timeout: 10_000 });

    // Variance badge must be visible and negative (counted 0, system qty ≥ 1 from delivered order)
    const varianceBadge = page.locator('.bg-red-100.text-red-700').first();
    await expect(varianceBadge).toBeVisible({ timeout: 10_000 });
    const varianceText = await varianceBadge.textContent();
    const varianceValue = parseFloat(varianceText?.trim() ?? '0');
    expect(varianceValue).toBeLessThan(0);
  });

  test('finalized LOT count appears in the list with FINALIZED status', async ({ page }) => {
    // Serial mode ensures test 2 has already finalized lotCountId before this runs
    await page.goto('/stock-counts');
    await expect(page.locator('table tbody')).toBeVisible();

    // List should contain a row showing Lot type and FINALIZED
    const finalizedLotRow = page.locator('table tbody tr').filter({ hasText: 'FINALIZED' }).filter({ hasText: 'Lot' });
    await expect(finalizedLotRow.first()).toBeVisible({ timeout: 10_000 });
  });
});
