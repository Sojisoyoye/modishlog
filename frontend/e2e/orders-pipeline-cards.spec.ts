import { test, expect, request, type Page } from '@playwright/test';
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

/** Locate a pipeline card by its human-readable heading text. */
function pipelineCard(page: Page, label: string) {
  // The h4 heading is two levels below the card div: card > header-div > h4
  return page.locator('h4').filter({ hasText: new RegExp(`^${label}$`, 'i') }).locator('../..');
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

  test('pipeline card headings show human-readable labels', async ({ page }) => {
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    // Each card h4 must show the friendly label (CSS text-transform:uppercase renders it visually
    // all-caps, but the DOM value is the mapped string from statusLabel).
    const expectedLabels = ['Ordered', 'Pending', 'In Production', 'Shipping', 'Cleared', 'Delivered'];
    for (const label of expectedLabels) {
      await expect(page.locator('h4').filter({ hasText: new RegExp(`^${label}$`, 'i') })).toBeVisible();
    }

    // The raw underscore enum values must NOT appear as h4 headings
    const rawValues = ['PENDING', 'IN_PRODUCTION', 'SHIPPING', 'CLEARED', 'DELIVERED'];
    for (const raw of rawValues) {
      await expect(page.locator('h4').filter({ hasText: new RegExp(`^${raw}$`) })).toHaveCount(0);
    }
  });

  test('orders appear in the correct pipeline card for their status', async ({ page }) => {
    const pending = await createOrder(productId, 'PENDING');
    const shipping = await createOrder(productId, 'SHIPPING');
    const delivered = await createOrder(productId, 'DELIVERED');

    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    // Each created order number must appear inside its correct status card
    await expect(pipelineCard(page, 'Pending').getByText(pending.order_number)).toBeVisible();
    await expect(pipelineCard(page, 'Shipping').getByText(shipping.order_number)).toBeVisible();
    await expect(pipelineCard(page, 'Delivered').getByText(delivered.order_number)).toBeVisible();
  });

  test('pipeline card count is non-zero when orders exist in that status', async ({ page }) => {
    await createOrder(productId, 'IN_PRODUCTION');

    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    const card = pipelineCard(page, 'In Production');
    const badge = card.locator('span.rounded-full');
    const countText = await badge.textContent();
    expect(parseInt(countText?.trim() ?? '0')).toBeGreaterThan(0);
  });

  test('pipeline card badge count matches number of that-status orders in the table', async ({ page }) => {
    await createOrder(productId, 'PENDING');

    await page.goto('/orders');
    await page.waitForLoadState('networkidle');

    // Count rows in the table whose status badge text is exactly 'PENDING'
    const pendingRows = page.locator('table tbody tr').filter({
      has: page.locator('app-status-badge', { hasText: /^PENDING$/ }),
    });
    const tableCount = await pendingRows.count();

    // The Pending pipeline card badge must show the same count
    const badge = pipelineCard(page, 'Pending').locator('span.rounded-full');
    const cardCount = parseInt((await badge.textContent())?.trim() ?? '0');

    expect(cardCount).toBe(tableCount);
  });
});
