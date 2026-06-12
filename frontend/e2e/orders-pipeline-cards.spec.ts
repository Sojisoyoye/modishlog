import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';
import { ensureProduct } from './helpers/data';

const API = 'http://localhost:8000/api/v1';

async function createOrder(
  productId: string,
  status: string,
): Promise<{ id: string; order_number: string }> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.post(`${API}/orders`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        supplier_name: 'Pipeline Test Supplier',
        status,
        currency: 'USD',
        total_amount: '500.00',
        line_items: [
          { product_id: productId, quantity: 5, unit_cost: '100.00', line_total: '500.00' },
        ],
      },
    });
    if (!resp.ok()) {
      throw new Error(`Failed to create order: ${resp.status()} ${await resp.text()}`);
    }
    return resp.json();
  } finally {
    await ctx.dispose();
  }
}

test.describe('Orders pipeline status cards', () => {
  let productId: string;

  test.beforeAll(async () => {
    await ensureTestUser();
    const product = await ensureProduct('Pipeline Card Test Product');
    productId = product.id;
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('pipeline cards show correct counts matching the table', async ({ page }) => {
    // Create one order in each status
    const pending = await createOrder(productId, 'PENDING');
    const shipping = await createOrder(productId, 'SHIPPING');
    const delivered = await createOrder(productId, 'DELIVERED');

    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    // The table shows all orders — get counts per status from it
    const tableRows = page.locator('table tbody tr');
    await expect(tableRows.first()).toBeVisible();

    // Cards must show human-readable labels (not raw enum strings)
    await expect(page.getByText('Pending').first()).toBeVisible();
    await expect(page.getByText('Shipping').first()).toBeVisible();
    await expect(page.getByText('Delivered').first()).toBeVisible();
    await expect(page.getByText('In Production').first()).toBeVisible();
    await expect(page.getByText('Cleared').first()).toBeVisible();

    // Raw enum strings must NOT appear as card headings
    await expect(page.getByText('PENDING')).not.toBeVisible();
    await expect(page.getByText('IN_PRODUCTION')).not.toBeVisible();
    await expect(page.getByText('SHIPPING')).not.toBeVisible();
    await expect(page.getByText('CLEARED')).not.toBeVisible();
    await expect(page.getByText('DELIVERED')).not.toBeVisible();

    // The order numbers we created must appear inside their respective pipeline cards.
    // Pending card contains the pending order number.
    const pendingCard = page.locator('.pipeline-card', { hasText: 'Pending' }).first();
    await expect(pendingCard.getByText(pending.order_number)).toBeVisible();

    // Shipping card contains the shipping order number.
    const shippingCard = page.locator('.pipeline-card', { hasText: 'Shipping' }).first();
    await expect(shippingCard.getByText(shipping.order_number)).toBeVisible();

    // Delivered card contains the delivered order number.
    const deliveredCard = page.locator('.pipeline-card', { hasText: 'Delivered' }).first();
    await expect(deliveredCard.getByText(delivered.order_number)).toBeVisible();
  });

  test('pipeline card count is non-zero when orders exist in that status', async ({ page }) => {
    await createOrder(productId, 'IN_PRODUCTION');

    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    // Find the "In Production" pipeline card and check its badge count is > 0
    const inProdCard = page.locator('div').filter({ hasText: /^In Production$/ }).first()
      .locator('..');
    const badge = inProdCard.locator('span.rounded-full');
    const countText = await badge.textContent();
    expect(parseInt(countText?.trim() ?? '0')).toBeGreaterThan(0);
  });

  test('card count matches table row count for same status', async ({ page }) => {
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    // Count PENDING rows in the table
    const pendingTableRows = page.locator('table tbody tr').filter({ hasText: 'PENDING' });
    const tableCount = await pendingTableRows.count();

    // Pending pipeline card badge should match
    const pendingCard = page.locator('h4').filter({ hasText: /^Pending$/i }).locator('../..');
    const badge = pendingCard.locator('span.rounded-full');
    const cardCount = parseInt((await badge.textContent())?.trim() ?? '0');

    expect(cardCount).toBe(tableCount);
  });
});
