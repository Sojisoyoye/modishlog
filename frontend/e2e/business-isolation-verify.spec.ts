/**
 * Verifies that a newly registered business sees an empty dashboard,
 * even when the browser previously had another business's session active.
 *
 * Run headed against the dev stack (no global-setup):
 *   npx playwright test --config e2e/isolation-verify.config.ts --headed
 *
 * NOTE: excluded from the main playwright.config.ts suite (requires live dev DB
 * with ade@gmail.com present — not available after global-setup wipes to test DB).
 */

import { test, expect } from '@playwright/test';

const DEV_EMAIL = 'ade@gmail.com';
const DEV_PASSWORD = 'Modish1234!';
const NEW_PASSWORD = 'E2eReg!Pass#14';
const NEW_NAME = 'Isolation Verify User';
const NEW_BIZ = 'Brand New Biz';

test('new registration sees empty dashboard — not previous user data', async ({ page }) => {
  // NEW_EMAIL inside test body so each run (and any retry) gets a unique address
  const NEW_EMAIL = `isolation-verify-${Date.now()}@test.com`;

  // ── Step 1: Login as existing dev user (Ade Fashion — 150 products, 890 sales) ──
  await page.goto('/login');
  await page.locator('#email, input[type="email"]').fill(DEV_EMAIL);
  await page.locator('#password, input[type="password"]').fill(DEV_PASSWORD);
  await page.getByRole('button', { name: /log in|sign in/i }).click();

  await page.waitForURL('**/dashboard', { timeout: 15_000 });
  await page.waitForLoadState('networkidle', { timeout: 15_000 });

  // Precondition: confirm the dev DB actually has historical data before we test isolation.
  // If this fails the test aborts early with a clear message rather than a false green.
  await page.screenshot({ path: 'e2e/screenshots/01-ade-fashion-dashboard.png', fullPage: true });
  const bodyText = await page.locator('body').innerText();
  const hasSalesData = /[1-9]/.test(bodyText.replace(/₦0\.00|₦0 /g, ''));
  expect(hasSalesData, 'Precondition: Ade Fashion must have historical data for this test to be meaningful').toBe(true);

  // ── Step 2: Register as a new user while the old session cookie is still active ──
  await page.goto('/register');
  await page.waitForLoadState('domcontentloaded');

  await page.locator('#reg-full-name').fill(NEW_NAME);
  await page.locator('#reg-email').fill(NEW_EMAIL);
  await page.locator('#reg-password').fill(NEW_PASSWORD);
  await page.locator('#reg-confirm-password').fill(NEW_PASSWORD);
  await page.getByRole('button', { name: /next/i }).click();

  await expect(page.locator('#reg-business-name')).toBeVisible({ timeout: 8_000 });
  await page.locator('#reg-business-name').fill(NEW_BIZ);
  await page.getByRole('button', { name: /create account/i }).click();

  // ── Step 3: Wait for full-page reload to dashboard ──
  // window.location.href in register-page triggers a real navigation; Playwright
  // treats it as a full load, not just a URL change.
  await page.waitForURL('**/dashboard', { timeout: 20_000 });
  // Wait for KPI cards to render (first visible card = data has loaded)
  await expect(page.locator('body')).toContainText(/Today|Revenue|Sales|₦/, { timeout: 15_000 });

  await page.screenshot({ path: 'e2e/screenshots/02-new-business-dashboard.png', fullPage: true });

  // ── Step 4: Assert dashboard shows zero totals — not Ade Fashion's numbers ──
  const dashBody = await page.locator('body').innerText();

  // Negative check: Ade Fashion's specific totals must not appear
  const hasOldData =
    dashBody.includes('32,129') ||
    dashBody.includes('32129') ||
    dashBody.includes('890');
  expect(hasOldData, 'Dashboard must NOT show previous business data after new registration').toBe(false);

  // Positive check: KPI cards show "0 transactions" or "₦" prefix + "0" in adjacent elements.
  // Use the transaction count label which is reliably a single text node.
  await expect(page.locator('body')).toContainText(/0\s*transactions?|No sales|0\.00/, { timeout: 5_000 });

  // ── Step 5: Products page ──
  await page.goto('/products');
  await page.waitForLoadState('networkidle', { timeout: 15_000 });
  await expect(page.locator('body')).toContainText(/Products|product/, { timeout: 10_000 });

  await page.screenshot({ path: 'e2e/screenshots/03-new-business-products.png', fullPage: true });
  const productsBody = await page.locator('body').innerText();
  const hasOldProducts = productsBody.includes('150') || productsBody.includes('PRD-');
  expect(hasOldProducts, 'Products page must NOT show previous business products').toBe(false);

  // ── Step 6: Orders page ──
  await page.goto('/orders');
  await page.waitForLoadState('networkidle', { timeout: 15_000 });
  await expect(page.locator('body')).toContainText(/Orders|order/, { timeout: 10_000 });

  await page.screenshot({ path: 'e2e/screenshots/04-new-business-orders.png', fullPage: true });
  const ordersBody = await page.locator('body').innerText();
  const hasOldOrders = ordersBody.includes('PO-') || ordersBody.includes('888') || ordersBody.includes('890');
  expect(hasOldOrders, 'Orders page must NOT show previous business orders').toBe(false);
});
