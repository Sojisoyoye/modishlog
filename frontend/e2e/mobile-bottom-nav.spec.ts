import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.describe('mobile bottom navigation', () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('bottom nav is visible on mobile and sidebar is not', async ({ page }) => {
    await expect(page.getByTestId('bottom-nav')).toBeVisible();
    // Sidebar should be off-screen (translated away) on mobile
    const sidebar = page.locator('aside');
    const box = await sidebar.boundingBox();
    // Either not visible or translated off-screen (x < 0)
    expect(box === null || box.x < 0).toBeTruthy();
  });

  test('bottom nav contains Dashboard, Sales, Inventory, More tabs', async ({ page }) => {
    const nav = page.getByTestId('bottom-nav');
    await expect(nav.getByRole('link', { name: /dashboard/i })).toBeVisible();
    await expect(nav.getByRole('link', { name: /sales/i })).toBeVisible();
    await expect(nav.getByRole('link', { name: /inventory/i })).toBeVisible();
    await expect(nav.getByRole('button', { name: /more/i })).toBeVisible();
  });

  test('tapping Dashboard navigates to /dashboard', async ({ page }) => {
    await page.goto('/sales');
    await page.getByTestId('bottom-nav').getByRole('link', { name: /dashboard/i }).click();
    await expect(page).toHaveURL('/dashboard');
  });

  test('tapping Sales navigates to /sales', async ({ page }) => {
    await page.getByTestId('bottom-nav').getByRole('link', { name: /sales/i }).click();
    await expect(page).toHaveURL('/sales');
  });

  test('tapping Inventory navigates to /inventory', async ({ page }) => {
    await page.getByTestId('bottom-nav').getByRole('link', { name: /inventory/i }).click();
    await expect(page).toHaveURL('/inventory');
  });

  test('tapping More opens the sidebar overlay and hides the bottom nav', async ({ page }) => {
    const sidebar = page.locator('aside');
    const bottomNav = page.getByTestId('bottom-nav');
    // Initially sidebar is hidden — tap More to reveal it
    await bottomNav.getByRole('button', { name: /more/i }).click();
    // Sidebar slides in
    await expect(sidebar).toBeVisible({ timeout: 2000 });
    const box = await sidebar.boundingBox();
    expect(box !== null && box.x >= 0).toBeTruthy();
    // Bottom nav hides itself to avoid overlapping the open sidebar
    await expect(bottomNav).not.toBeVisible();
  });

  test('hamburger toggle is hidden on mobile', async ({ page }) => {
    // The topbar hamburger/toggle button should not be visible at 375px
    await expect(page.getByTestId('topbar-menu-toggle')).not.toBeVisible();
  });
});

test.describe('bottom nav hidden on desktop', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('bottom nav is hidden on desktop', async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('bottom-nav')).not.toBeVisible();
  });

  test('sidebar is visible on desktop', async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    const sidebar = page.locator('aside');
    const box = await sidebar.boundingBox();
    expect(box !== null && box.x >= 0).toBeTruthy();
  });
});
