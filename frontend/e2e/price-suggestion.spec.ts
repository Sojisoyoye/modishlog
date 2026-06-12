import { test, expect, request } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';
import { ensureProduct, ensureCategory, ensureProductInCategory } from './helpers/data';

const API = 'http://localhost:8000/api/v1';

async function seedDeliveredOrder(productId: string): Promise<{ id: string }> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const orderResp = await ctx.post(`${API}/orders`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        supplier_name: 'E2E Price Suggestion Supplier',
        currency: 'USD',
        fx_rate_at_creation: 1600,
        order_date: new Date().toISOString().split('T')[0],
        line_items: [{ product_id: productId, quantity: 10, unit_cost: '50.00' }],
      },
    });
    if (!orderResp.ok()) throw new Error(`Create order failed: ${orderResp.status()} ${await orderResp.text()}`);
    const order = await orderResp.json();

    // Transition through full lifecycle to DELIVERED
    for (const status of ['IN_PRODUCTION', 'SHIPPING', 'CLEARED', 'DELIVERED']) {
      const tr = await ctx.put(`${API}/orders/${order.id}/status`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { new_status: status },
      });
      if (!tr.ok()) throw new Error(`Transition to ${status} failed: ${tr.status()} ${await tr.text()}`);
    }
    return { id: order.id };
  } finally {
    await ctx.dispose();
  }
}

async function deleteOrder(orderId: string): Promise<void> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.delete(`${API}/orders/${orderId}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!resp.ok()) {
      // DELIVERED orders cannot be cancelled — this is expected; log so it's visible in CI output
      console.warn(`deleteOrder: ${orderId} returned ${resp.status()} — order may be DELIVERED and cannot be cancelled`);
    }
  } finally {
    await ctx.dispose();
  }
}

async function deleteProduct(productId: string): Promise<void> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    await ctx.delete(`${API}/products/${productId}`, { headers: { Authorization: `Bearer ${token}` } });
  } finally {
    await ctx.dispose();
  }
}

// Use serial mode so beforeAll/afterAll run exactly once and tests share state
test.describe.configure({ mode: 'serial' });

test.describe('Price suggestion engine (#76)', () => {
  let productId: string;
  let productName: string;
  let orderId: string;

  test.beforeAll(async () => {
    await ensureTestUser();
    const product = await ensureProduct('E2E Suggest Price Product');
    productId = product.id;
    productName = product.name;
    const order = await seedDeliveredOrder(productId);
    orderId = order.id;

    // Seed a USDNGN rate directly so compute_suggestion never calls the external API.
    // Using ingest (not GET /fx/live) avoids any dependency on open.er-api.com under
    // concurrent load, which caused intermittent 500s when the first test ran.
    const token = await getAPIToken();
    const ctx = await request.newContext();
    try {
      const resp = await ctx.post(`${API}/fx/rates/ingest`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { pair: 'USDNGN', rate: 1600, source: 'manual' },
      });
      if (!resp.ok()) throw new Error(`FX seed failed: ${resp.status()} ${await resp.text()}`);
    } finally {
      await ctx.dispose();
    }
  });

  test.afterAll(async () => {
    if (orderId) await deleteOrder(orderId);
    if (productId) await deleteProduct(productId);
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  /** Search for the product on the products page and return the matching row. */
  async function findProductRow(page: import('@playwright/test').Page) {
    await page.goto('/products');
    await page.waitForLoadState('networkidle');
    // Use the search box to filter — avoids pagination
    await page.getByPlaceholder('Search products...').fill(productName);
    await page.waitForTimeout(400); // debounce
    await expect(page.getByText(productName).first()).toBeVisible({ timeout: 8_000 });
    return page.locator('tr').filter({ hasText: productName });
  }

  test('Products page loads and shows the product via search', async ({ page }) => {
    await findProductRow(page);
    // row was found — test passes if no error thrown
  });

  test('action menu contains Suggest Price item', async ({ page }) => {
    const row = await findProductRow(page);
    await row.getByRole('button', { name: /product actions/i }).click();
    await expect(page.getByRole('menuitem', { name: /suggest price/i })).toBeVisible();
    await page.keyboard.press('Escape');
  });

  test('clicking Suggest Price opens the suggestion panel with margin slider', async ({ page }) => {
    const row = await findProductRow(page);
    await row.getByRole('button', { name: /product actions/i }).click();
    await page.getByRole('menuitem', { name: /suggest price/i }).click();

    await expect(page.getByRole('heading', { name: /suggest sell price/i })).toBeVisible();

    const slider = page.locator('input[type="range"]');
    await expect(slider).toBeVisible();
    await expect(slider).toHaveAttribute('min', '20');
    await expect(slider).toHaveAttribute('max', '70');

    await expect(page.getByText(/target margin.*40%/i)).toBeVisible();
  });

  test('computing a suggestion shows price, cost, FX rate and margin', async ({ page }) => {
    const row = await findProductRow(page);
    await row.getByRole('button', { name: /product actions/i }).click();
    await page.getByRole('menuitem', { name: /suggest price/i }).click();

    await page.getByRole('button', { name: /compute suggestion/i }).click();

    await expect(page.getByText(/suggested price/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('p').filter({ hasText: /₦[\d,]+/ }).first()).toBeVisible();
    await expect(page.getByText(/weighted landed cost/i)).toBeVisible();
    await expect(page.getByText(/fx rate used/i)).toBeVisible();
    await expect(page.getByText('Margin: 40%', { exact: true })).toBeVisible();
  });

  test('changing margin slider to 55% and recomputing updates the result', async ({ page }) => {
    const row = await findProductRow(page);
    await row.getByRole('button', { name: /product actions/i }).click();
    await page.getByRole('menuitem', { name: /suggest price/i }).click();

    const slider = page.locator('input[type="range"]');
    await slider.fill('55');
    await slider.dispatchEvent('input');
    await slider.dispatchEvent('change');
    await expect(page.getByText(/target margin.*55%/i)).toBeVisible();

    await page.getByRole('button', { name: /compute suggestion/i }).click();
    await expect(page.locator('p').filter({ hasText: /₦[\d,]+/ }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('Margin: 55%', { exact: true })).toBeVisible();
  });

  test('suggestion history has at least 2 entries after two computations', async ({ page }) => {
    const row = await findProductRow(page);

    // First suggestion at 30%
    await row.getByRole('button', { name: /product actions/i }).click();
    await page.getByRole('menuitem', { name: /suggest price/i }).click();
    let slider = page.locator('input[type="range"]');
    await slider.fill('30');
    await slider.dispatchEvent('input');
    await slider.dispatchEvent('change');
    await page.getByRole('button', { name: /compute suggestion/i }).click();
    await expect(page.locator('p').filter({ hasText: /₦[\d,]+/ }).first()).toBeVisible({ timeout: 15_000 });
    // Close panel
    // Close the panel — scope to the panel to avoid matching "Clear filters" button
    const panel = page.locator('div').filter({ has: page.getByRole('heading', { name: /suggest sell price/i }) }).last();
    await panel.getByRole('button').filter({ has: page.locator('.pi-times') }).click();
    await expect(page.getByRole('heading', { name: /suggest sell price/i })).not.toBeVisible();

    // Second suggestion at 60%
    await row.getByRole('button', { name: /product actions/i }).click();
    await page.getByRole('menuitem', { name: /suggest price/i }).click();
    slider = page.locator('input[type="range"]');
    await slider.fill('60');
    await slider.dispatchEvent('input');
    await slider.dispatchEvent('change');
    await page.getByRole('button', { name: /compute suggestion/i }).click();
    await expect(page.locator('p').filter({ hasText: /₦[\d,]+/ }).first()).toBeVisible({ timeout: 15_000 });

    // Verify via API — at least 2 history entries
    const token = await getAPIToken();
    const ctx = await request.newContext();
    try {
      const histResp = await ctx.get(`${API}/pricing/suggest/${productId}/history`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(histResp.ok()).toBeTruthy();
      const history = await histResp.json();
      expect(Array.isArray(history)).toBeTruthy();
      expect(history.length).toBeGreaterThanOrEqual(2);
      // Use some() instead of index access — history accumulates across test runs,
      // so [0]/[1] would fail if earlier runs left entries for this product.
      type Entry = { target_margin_pct: string };
      expect(history.some((h: Entry) => Math.abs(parseFloat(h.target_margin_pct) - 0.60) < 0.05)).toBeTruthy();
      expect(history.some((h: Entry) => Math.abs(parseFloat(h.target_margin_pct) - 0.30) < 0.05)).toBeTruthy();
    } finally {
      await ctx.dispose();
    }
  });

  test('closing the panel hides the suggestion result', async ({ page }) => {
    const row = await findProductRow(page);
    await row.getByRole('button', { name: /product actions/i }).click();
    await page.getByRole('menuitem', { name: /suggest price/i }).click();
    await expect(page.getByRole('heading', { name: /suggest sell price/i })).toBeVisible();

    // Close the panel — scope to the panel to avoid matching "Clear filters" button
    const panel = page.locator('div').filter({ has: page.getByRole('heading', { name: /suggest sell price/i }) }).last();
    await panel.getByRole('button').filter({ has: page.locator('.pi-times') }).click();
    await expect(page.getByRole('heading', { name: /suggest sell price/i })).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Category-aware default margin pre-fill (Task #80)
// ---------------------------------------------------------------------------

test.describe('Category-aware price suggestion margin (#80)', () => {
  let categoryId: string;
  let productId: string;
  let productName: string;
  let orderId: string;

  test.describe.configure({ mode: 'serial' });

  test.beforeAll(async () => {
    await ensureTestUser();

    // Create a category with a 35% default margin
    const token = await getAPIToken();
    const ctx = await request.newContext();
    try {
      const catName = `E2E Margin Cat ${Date.now()}`;
      const catResp = await ctx.post(`${API}/products/categories`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { name: catName, description: 'category with default margin', default_margin_pct: 0.35 },
      });
      if (!catResp.ok()) throw new Error(`Create category failed: ${catResp.status()} ${await catResp.text()}`);
      categoryId = (await catResp.json()).id;

      // Create a product in that category
      const p = await ensureProductInCategory(categoryId, `E2E Cat Margin Product ${Date.now()}`);
      productId = p.id;
      productName = p.name;

      // Seed delivered order so compute_suggestion can run
      const orderResp = await ctx.post(`${API}/orders`, {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          supplier_name: 'E2E Cat Margin Supplier',
          currency: 'USD',
          fx_rate_at_creation: 1600,
          order_date: new Date().toISOString().split('T')[0],
          line_items: [{ product_id: productId, quantity: 10, unit_cost: '50.00' }],
        },
      });
      if (!orderResp.ok()) throw new Error(`Create order failed: ${orderResp.status()} ${await orderResp.text()}`);
      const order = await orderResp.json();
      orderId = order.id;

      for (const status of ['IN_PRODUCTION', 'SHIPPING', 'CLEARED', 'DELIVERED']) {
        const tr = await ctx.put(`${API}/orders/${order.id}/status`, {
          headers: { Authorization: `Bearer ${token}` },
          data: { new_status: status },
        });
        if (!tr.ok()) throw new Error(`Transition to ${status} failed`);
      }
    } finally {
      await ctx.dispose();
    }
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  async function findProductRow(page: import('@playwright/test').Page) {
    await page.goto('/products');
    await page.waitForLoadState('networkidle');
    await page.getByPlaceholder('Search products...').fill(productName);
    await page.waitForTimeout(400);
    await expect(page.getByText(productName).first()).toBeVisible({ timeout: 8_000 });
    return page.locator('tr').filter({ hasText: productName });
  }

  test('slider pre-fills with category default margin (35%) on panel open', async ({ page }) => {
    const row = await findProductRow(page);
    await row.getByRole('button', { name: /product actions/i }).click();
    await page.getByRole('menuitem', { name: /suggest price/i }).click();

    await expect(page.getByRole('heading', { name: /suggest sell price/i })).toBeVisible();

    // Slider should be pre-filled to 35 (category default)
    const slider = page.locator('input[type="range"]');
    await expect(slider).toHaveValue('35');
    await expect(page.getByText(/target margin.*35%/i)).toBeVisible();
  });

  test('moving slider to 55% and computing uses 55%, not category default', async ({ page }) => {
    const row = await findProductRow(page);
    await row.getByRole('button', { name: /product actions/i }).click();
    await page.getByRole('menuitem', { name: /suggest price/i }).click();

    const slider = page.locator('input[type="range"]');
    await slider.fill('55');
    await slider.dispatchEvent('input');
    await slider.dispatchEvent('change');
    await expect(page.getByText(/target margin.*55%/i)).toBeVisible();

    await page.getByRole('button', { name: /compute suggestion/i }).click();
    await expect(page.locator('p').filter({ hasText: /₦[\d,]+/ }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('Margin: 55%', { exact: true })).toBeVisible();
  });
});
