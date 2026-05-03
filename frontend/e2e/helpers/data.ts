import { request } from '@playwright/test';
import { getAPIToken } from './auth';

const API = 'http://localhost:8000/api/v1';

/**
 * Create a product via the API and return its ID.
 * Uses a random SKU to avoid conflicts across test runs.
 */
export async function ensureProduct(
  name = 'E2E Test Product',
): Promise<{ id: string; name: string }> {
  const token = await getAPIToken();
  const ctx = await request.newContext();
  try {
    const sku = `E2E-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const resp = await ctx.post(`${API}/products`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name,
        sku,
        unit_cost: '3000.00',
        selling_price: '5000.00',
        currency: 'NGN',
      },
    });
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
