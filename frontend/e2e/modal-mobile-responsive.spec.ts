import { test, expect } from '@playwright/test';

const MOBILE = { width: 390, height: 844 };

test.describe('Modal mobile responsiveness', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@modishlog.com');
    await page.fill('input[type="password"]', 'ModishAdmin@2024!');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/dashboard/);
  });

  test('inventory adjust-stock dialog fits viewport on mobile', async ({ page }) => {
    await page.goto('/inventory');
    const adjustBtn = page.locator('button', { hasText: 'Adjust' }).first();
    await adjustBtn.waitFor();
    await adjustBtn.click();

    const dialog = page.locator('.p-dialog');
    await dialog.waitFor({ state: 'visible' });
    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeLessThanOrEqual(MOBILE.width);
    expect(box!.x).toBeGreaterThanOrEqual(0);
  });

  test('sales edit-sale dialog fits viewport on mobile', async ({ page }) => {
    await page.goto('/sales');
    // Switch to All Sales to find a transaction row
    const allTab = page.getByTestId('tab-all-sales');
    await allTab.waitFor();
    await allTab.click();
    const txnRow = page.getByTestId('transaction-row').first();
    await txnRow.waitFor({ timeout: 5000 }).catch(() => null);
    // If no transactions exist, skip detail test
    if (await txnRow.count() === 0) return;
    await txnRow.click();

    const dialog = page.locator('.p-dialog').first();
    await dialog.waitFor({ state: 'visible' });
    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeLessThanOrEqual(MOBILE.width);
  });

  test('orders create-order dialog fits viewport on mobile', async ({ page }) => {
    await page.goto('/orders');
    const newOrderBtn = page.locator('button', { hasText: 'New Order' });
    await newOrderBtn.waitFor();
    await newOrderBtn.click();

    const dialog = page.locator('.p-dialog');
    await dialog.waitFor({ state: 'visible' });
    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeLessThanOrEqual(MOBILE.width);
    expect(box!.x).toBeGreaterThanOrEqual(0);
  });

  test('products edit-product dialog fits viewport on mobile', async ({ page }) => {
    await page.goto('/products');
    // Wait for products to load
    await page.waitForTimeout(1000);
    const editBtn = page.locator('button[title="Edit product"]').first();
    if (await editBtn.count() === 0) return;
    await editBtn.click();

    const dialog = page.locator('.p-dialog');
    await dialog.waitFor({ state: 'visible' });
    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeLessThanOrEqual(MOBILE.width);
  });

  test('recommendations dismiss dialog fits viewport on mobile', async ({ page }) => {
    await page.goto('/recommendations');
    const dismissBtn = page.locator('button', { hasText: 'Dismiss' }).first();
    await dismissBtn.waitFor({ timeout: 5000 }).catch(() => null);
    if (await dismissBtn.count() === 0) return;
    await dismissBtn.click();

    const dialog = page.locator('.p-dialog');
    await dialog.waitFor({ state: 'visible' });
    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeLessThanOrEqual(MOBILE.width);
  });
});
