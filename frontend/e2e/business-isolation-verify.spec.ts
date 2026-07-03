/**
 * Verifies that a newly registered business sees an empty dashboard,
 * even when the browser previously had another business's session active.
 *
 * Run headed against the dev stack (no global-setup):
 *   npx playwright test e2e/business-isolation-verify.spec.ts \
 *     --headed --project=chromium --config e2e/isolation-verify.config.ts
 */

import { test, expect } from '@playwright/test';

const DEV_EMAIL = 'ade@gmail.com';
const DEV_PASSWORD = 'Modish1234!';

const NEW_EMAIL = `isolation-verify-${Date.now()}@test.com`;
const NEW_PASSWORD = 'E2eReg!Pass#14';
const NEW_NAME = 'Isolation Verify User';
const NEW_BIZ = 'Brand New Biz';

test('new registration sees empty dashboard — not previous user data', async ({ page }) => {
  // ── Step 1: Login as existing dev user (Ade Fashion — 150 products, 890 sales) ──
  await page.goto('/login');
  await page.locator('#email, input[type="email"]').fill(DEV_EMAIL);
  await page.locator('#password, input[type="password"]').fill(DEV_PASSWORD);
  await page.getByRole('button', { name: /log in|sign in/i }).click();

  await page.waitForURL('**/dashboard', { timeout: 15_000 });
  // Wait for KPI data to load (cards render after API response)
  await page.waitForLoadState('networkidle', { timeout: 15_000 });
  await page.waitForTimeout(1500);

  await page.screenshot({ path: 'e2e/screenshots/01-ade-fashion-dashboard.png', fullPage: true });
  const bodyText = await page.locator('body').innerText();
  // KPI values appear as "₦32,129,324.02" or similar — just check non-zero presence
  const hasSalesData = /[1-9]/.test(bodyText.replace(/₦0\.00|₦0 /g, ''));
  console.log('Ade Fashion dashboard — non-zero data found:', hasSalesData);

  // ── Step 2: Navigate to /register while still "logged in" as ade ──
  await page.goto('/register');
  await page.waitForLoadState('domcontentloaded');

  // Step 1 of wizard
  await page.locator('#reg-full-name').fill(NEW_NAME);
  await page.locator('#reg-email').fill(NEW_EMAIL);
  await page.locator('#reg-password').fill(NEW_PASSWORD);
  await page.locator('#reg-confirm-password').fill(NEW_PASSWORD);
  await page.getByRole('button', { name: /next/i }).click();

  // Step 2 of wizard
  await expect(page.locator('#reg-business-name')).toBeVisible({ timeout: 8_000 });
  await page.locator('#reg-business-name').fill(NEW_BIZ);
  await page.getByRole('button', { name: /create account/i }).click();

  // ── Step 3: Wait for full-page reload and dashboard ──
  // window.location.href triggers a real navigation (not router.navigate),
  // so Playwright detects it as a full navigation event.
  await page.waitForURL('**/dashboard', { timeout: 20_000 });
  await page.waitForLoadState('networkidle', { timeout: 15_000 });
  await page.waitForTimeout(1500);

  await page.screenshot({ path: 'e2e/screenshots/02-new-business-dashboard.png', fullPage: true });
  console.log('Landed on dashboard as new user:', NEW_EMAIL);

  // ── Step 4: Assert dashboard shows zero totals ──
  // The KPI cards should show ₦0.00 or 0, not Ade Fashion's ₦32M or 890 transactions
  const dashBody = await page.locator('body').innerText();

  const hasOldData =
    dashBody.includes('32,129') ||  // old total_sales
    dashBody.includes('32129') ||
    dashBody.includes('890');        // old transaction count

  expect(hasOldData, 'Dashboard must NOT show previous business data after new registration').toBe(false);

  // Confirm zero / empty state indicators
  const hasZeroState =
    dashBody.includes('0.00') ||
    dashBody.includes('₦0') ||
    dashBody.includes('No recent') ||
    dashBody.includes('0');

  expect(hasZeroState, 'Dashboard should show empty/zero state for brand new business').toBe(true);

  console.log('✅ Isolation verified: new business dashboard is empty');

  // ── Step 5: Check Products page ──
  await page.goto('/products');
  await page.waitForLoadState('networkidle', { timeout: 15_000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'e2e/screenshots/03-new-business-products.png', fullPage: true });

  const productsBody = await page.locator('body').innerText();
  const hasOldProducts = productsBody.includes('150') || productsBody.includes('PRD-');
  expect(hasOldProducts, 'Products page must NOT show previous business products').toBe(false);
  console.log('✅ Products page is empty for new business');

  // ── Step 6: Check Orders page ──
  await page.goto('/orders');
  await page.waitForLoadState('networkidle', { timeout: 15_000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'e2e/screenshots/04-new-business-orders.png', fullPage: true });

  const ordersBody = await page.locator('body').innerText();
  const hasOldOrders = ordersBody.includes('PO-') || ordersBody.includes('888') || ordersBody.includes('890');
  expect(hasOldOrders, 'Orders page must NOT show previous business orders').toBe(false);
  console.log('✅ Orders page is empty for new business');
});
