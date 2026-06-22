import { request } from '@playwright/test';
import { getAPIToken } from './auth';

const API = 'http://localhost:8000/api/v1';

/**
 * Ensure an E2E category exists and return its ID (idempotent).
 * Uses GET-first to avoid the 500 the categories endpoint throws on duplicate name.
 */
async function ensureE2ECategory(): Promise<string> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    // Check existence first to avoid duplicate-key 500
    const listResp = await ctx.get(`${API}/products/categories`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (listResp.ok()) {
      const cats: { id: string; name: string }[] = await listResp.json();
      const found = cats.find((c) => c.name === 'E2E Test Category');
      if (found) return found.id;
    }
    // Not found — create it
    const resp = await ctx.post(`${API}/products/categories`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { name: 'E2E Test Category', description: 'Created by E2E helpers' },
    });
    if (!resp.ok()) throw new Error(`Create category failed: ${resp.status()} ${await resp.text()}`);
    return (await resp.json()).id;
  } finally {
    await ctx.dispose();
  }
}

/**
 * Ensure a product with the given name exists and return its ID (idempotent).
 * Searches first to avoid slug-conflict 409s on re-runs.
 */
export async function ensureProduct(
  name = 'E2E Test Product',
): Promise<{ id: string; name: string }> {
  const token = await getAPIToken();
  const categoryId = await ensureE2ECategory();
  const ctx = await request.newContext();
  try {
    // Check if product already exists by name
    const listResp = await ctx.get(`${API}/products?search=${encodeURIComponent(name)}&limit=25`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (listResp.ok()) {
      const data = await listResp.json();
      const items: { id: string; name: string }[] = Array.isArray(data) ? data : (data.items ?? data.products ?? []);
      const found = items.find((p) => p.name === name);
      if (found) return { id: found.id, name: found.name };
    }
    // Not found — create it
    const sku = `E2E-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const resp = await ctx.post(`${API}/products`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name,
        sku,
        unit_cost: '3000.00',
        selling_price: '5000.00',
        currency: 'NGN',
        category_id: categoryId,
      },
    });
    if (!resp.ok()) throw new Error(`Create product failed: ${resp.status()} ${await resp.text()}`);
    const product = await resp.json();
    return { id: product.id, name: product.name };
  } finally {
    await ctx.dispose();
  }
}

/**
 * Create a category via the API and return its ID and name.
 */
export async function ensureCategory(
  name = 'E2E Test Category',
): Promise<{ id: string; name: string }> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.post(`${API}/products/categories`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { name, description: 'Created by E2E test' },
    });
    if (!resp.ok()) {
      throw new Error(`Failed to create category: ${resp.status()} ${await resp.text()}`);
    }
    const category = await resp.json();
    return { id: category.id, name: category.name };
  } finally {
    await ctx.dispose();
  }
}

/**
 * Create a product assigned to a specific category via the API.
 */
export async function ensureProductInCategory(
  categoryId: string,
  name = 'E2E Category Product',
): Promise<{ id: string; name: string }> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const sku = `E2E-CAT-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const resp = await ctx.post(`${API}/products`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name,
        sku,
        unit_cost: '2000.00',
        selling_price: '3500.00',
        currency: 'NGN',
        category_id: categoryId,
      },
    });
    if (!resp.ok()) {
      throw new Error(`Failed to create product in category: ${resp.status()} ${await resp.text()}`);
    }
    const product = await resp.json();
    return { id: product.id, name: product.name };
  } finally {
    await ctx.dispose();
  }
}

/**
 * Create a purchase order for a product and return the order ID.
 * Optionally pass supplierId to link the order to a Supplier record (needed
 * for the supplier's Purchases tab to show this order).
 */
export async function createOrder(
  productId: string,
  options: { currency?: string; quantity?: number; unitCost?: string; supplierId?: string } = {},
): Promise<{ id: string }> {
  const { currency = 'USD', quantity = 10, unitCost = '100.00', supplierId } = options;
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const body: Record<string, unknown> = {
      supplier_name: 'E2E Test Supplier',
      currency,
      line_items: [{ product_id: productId, quantity, unit_cost: unitCost }],
    };
    if (supplierId) body['supplier_id'] = supplierId;
    const resp = await ctx.post(`${API}/orders`, {
      headers: { Authorization: `Bearer ${token}` },
      data: body,
    });
    if (!resp.ok()) throw new Error(`Create order failed: ${resp.status()} ${await resp.text()}`);
    return { id: (await resp.json()).id };
  } finally {
    await ctx.dispose();
  }
}

/**
 * Delete (cancel) a purchase order via the API.
 */
export async function deleteOrder(orderId: string): Promise<void> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.delete(`${API}/orders/${orderId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok() && resp.status() !== 404) {
      throw new Error(`Delete order failed: ${resp.status()} ${await resp.text()}`);
    }
  } finally {
    await ctx.dispose();
  }
}

/**
 * Advance a purchase order to the given status via the status-transition API.
 * Calls PUT /orders/:id/status for each hop in the transition chain.
 * Pass `fxRateAtDelivery` when transitioning to DELIVERED (required by the backend).
 */
export async function advanceOrderToStatus(
  orderId: string,
  targetStatus: string,
  options: { fxRateAtDelivery?: string } = {},
): Promise<void> {
  const statusOrder = ['ORDERED', 'PENDING', 'IN_PRODUCTION', 'SHIPPING', 'CLEARED', 'DELIVERED'];
  const targetIdx = statusOrder.indexOf(targetStatus);
  if (targetIdx === -1) throw new Error(`Unknown targetStatus: "${targetStatus}"`);

  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const orderResp = await ctx.get(`${API}/orders/${orderId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!orderResp.ok()) throw new Error(`Get order failed: ${orderResp.status()}`);
    const currentStatus: string = (await orderResp.json()).status;

    const currentIdx = statusOrder.indexOf(currentStatus);
    if (currentIdx === -1) throw new Error(`Unexpected current status: "${currentStatus}"`);
    if (targetIdx <= currentIdx) return;

    for (let i = currentIdx; i < targetIdx; i++) {
      const next = statusOrder[i + 1];
      const body: Record<string, unknown> = { new_status: next };
      if (next === 'DELIVERED' && options.fxRateAtDelivery) {
        body['fx_rate_at_delivery'] = options.fxRateAtDelivery;
      }
      const resp = await ctx.put(`${API}/orders/${orderId}/status`, {
        headers: { Authorization: `Bearer ${token}` },
        data: body,
      });
      if (!resp.ok()) throw new Error(`Status transition to ${next} failed: ${resp.status()} ${await resp.text()}`);
    }
  } finally {
    await ctx.dispose();
  }
}

/**
 * Create a sale for a product and return the sale ID.
 * Requires the product to have available stock (use addStock first).
 */
export async function createSale(
  productId: string,
  options: { quantity?: number; unitPrice?: string; saleDate?: string } = {},
): Promise<{ id: string }> {
  const { quantity = 1, unitPrice = '8000.00', saleDate = new Date().toISOString().split('T')[0] } = options;
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.post(`${API}/sales`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { product_id: productId, quantity, unit_price: unitPrice, sale_date: saleDate },
    });
    if (!resp.ok()) throw new Error(`Create sale failed: ${resp.status()} ${await resp.text()}`);
    return { id: (await resp.json()).id };
  } finally {
    await ctx.dispose();
  }
}

/**
 * Void (delete) a sale and restore inventory.
 */
export async function voidSale(saleId: string): Promise<void> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.delete(`${API}/sales/${saleId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok() && resp.status() !== 404) {
      throw new Error(`Void sale failed: ${resp.status()} ${await resp.text()}`);
    }
  } finally {
    await ctx.dispose();
  }
}

/**
 * Create a supplier via POST /suppliers and return its ID and name.
 */
export async function createSupplier(name: string): Promise<{ id: string; name: string }> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.post(`${API}/suppliers`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { name },
    });
    if (!resp.ok()) throw new Error(`Create supplier failed: ${resp.status()} ${await resp.text()}`);
    const s = await resp.json();
    return { id: s.id, name: s.name };
  } finally {
    await ctx.dispose();
  }
}

/**
 * Create a cashflow operating cost entry via POST /cashflow/operating-costs.
 */
export async function createOperatingCost(
  costName: string,
  costAmount: string,
  frequency: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'annually' = 'monthly',
  category = 'other',
): Promise<{ id: string }> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.post(`${API}/cashflow/operating-costs`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { cost_name: costName, cost_amount: costAmount, frequency, category },
    });
    if (!resp.ok()) throw new Error(`Create operating cost failed: ${resp.status()} ${await resp.text()}`);
    return { id: (await resp.json()).id };
  } finally {
    await ctx.dispose();
  }
}

/**
 * Fetch the current quantity_on_hand for a product via GET /inventory/:id.
 */
export async function getInventoryQty(productId: string): Promise<number> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const resp = await ctx.get(`${API}/inventory/${productId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok()) throw new Error(`Get inventory failed: ${resp.status()} ${await resp.text()}`);
    const data = await resp.json();
    return data.quantity_on_hand as number;
  } finally {
    await ctx.dispose();
  }
}

/**
 * Add stock to a product via the inventory adjust endpoint.
 */
export async function addStock(
  productId: string,
  quantity: number,
): Promise<void> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    await ctx.post(`${API}/inventory/${productId}/adjust`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        quantity_change: quantity,
        movement_type: 'manual_add',
        reason: 'E2E test stock seed',
      },
    });
  } finally {
    await ctx.dispose();
  }
}
