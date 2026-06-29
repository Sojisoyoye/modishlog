import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
});

// ---------------------------------------------------------------------------
// Sidebar layout
// ---------------------------------------------------------------------------

test('sidebar background fills full viewport height on short-content pages', async ({ page }) => {
  await page.goto('/dashboard');
  // Wait for the page to fully render before measuring layout geometry
  await expect(page.getByText('Good day,')).toBeVisible();

  const viewportHeight = page.viewportSize()!.height;
  // Scoped to app-sidebar to stay resilient if other <aside> elements are added
  const sidebar = page.locator('app-sidebar aside');

  const box = await sidebar.boundingBox();
  expect(box).not.toBeNull();
  // Sidebar height must match the full viewport — not just content height
  expect(box!.height).toBeGreaterThanOrEqual(viewportHeight);
});

test('sidebar background fills full viewport height on pages with minimal content', async ({
  page,
}) => {
  await page.goto('/fx');
  // Wait for the page to fully render before measuring layout geometry
  await expect(page.getByRole('heading', { name: 'FX Rates' })).toBeVisible();

  const viewportHeight = page.viewportSize()!.height;
  const sidebar = page.locator('app-sidebar aside');

  const box = await sidebar.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.height).toBeGreaterThanOrEqual(viewportHeight);
});
