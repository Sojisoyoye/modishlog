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
  // Dashboard is a good short-content candidate
  await page.goto('/dashboard');

  const viewportHeight = page.viewportSize()!.height;
  const sidebar = page.locator('aside');

  const box = await sidebar.boundingBox();
  expect(box).not.toBeNull();
  // Sidebar height must match the full viewport — not just content height
  expect(box!.height).toBeGreaterThanOrEqual(viewportHeight);
});

test('sidebar background fills full viewport height on pages with minimal content', async ({
  page,
}) => {
  // Settings / FX are typically light pages — good regression targets
  await page.goto('/fx');

  const viewportHeight = page.viewportSize()!.height;
  const sidebar = page.locator('aside');

  const box = await sidebar.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.height).toBeGreaterThanOrEqual(viewportHeight);
});
