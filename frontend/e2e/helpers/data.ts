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
