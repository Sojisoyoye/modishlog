import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import { ensureVariantProduct, createVariant } from './helpers/data';

// ---------------------------------------------------------------------------
// New Order form: variant picker must always reset unit_cost on a variant
// change, falling back to the product's own cost when the newly-selected
// variant has no cost_price_override — not silently keep the previous
// variant/product's stale value (task 175, found via PR #321 review).
// ---------------------------------------------------------------------------

let productId: string;
let productName: string;
let overrideVariantId: string;
let plainVariantId: string;

test.beforeAll(async () => {
  await ensureTestUser();
  const suffix = Date.now();
  const product = await ensureVariantProduct(`E2E Variant Cost Product ${suffix}`, '2000.00');
  productId = product.id;
  productName = product.name;

  const overrideVariant = await createVariant(productId, `Override-${suffix}`, '5000.00');
  const plainVariant = await createVariant(productId, `NoOverride-${suffix}`); // no cost_price_override
  overrideVariantId = overrideVariant.id;
  plainVariantId = plainVariant.id;
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
});

test('switching from a variant with a cost override to one without resets unit_cost to the product cost, not stale', async ({ page }) => {
  await page.goto('/orders');
  await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible({ timeout: 10_000 });

  await page.getByRole('button', { name: 'New Order' }).click();
  const dialog = page.locator('[role="dialog"]').filter({ hasText: 'New Order' });
  await expect(dialog).toBeVisible({ timeout: 5_000 });

  await dialog.getByTestId('order-item-product-select').selectOption({ label: productName });

  const variantSelect = dialog.getByTestId('order-item-variant-select');
  await expect(variantSelect).toBeVisible({ timeout: 5_000 });

  // Select the variant WITH a cost override — unit_cost must reflect it.
  await variantSelect.selectOption(overrideVariantId);
  const unitCostInput = dialog.getByTestId('order-item-unit-cost-input');
  await expect(unitCostInput).toHaveValue('5000.000000');

  // Switch to the variant WITHOUT an override — must reset to the
  // product's own unit_cost (2000), not keep showing the stale 5000.
  await variantSelect.selectOption(plainVariantId);
  await expect(unitCostInput).toHaveValue('2000.000000');
});
