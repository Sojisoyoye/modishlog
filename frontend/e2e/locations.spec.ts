import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

// ---------------------------------------------------------------------------
// Locations Page E2E Tests
// ---------------------------------------------------------------------------

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/settings/locations');
  await expect(page.getByRole('heading', { name: 'Locations', exact: true })).toBeVisible();
});

test('shows heading and Add Location button', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Locations', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add Location' })).toBeVisible();
});

test('opens add dialog', async ({ page }) => {
  await page.getByRole('button', { name: 'Add Location' }).click();

  const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Add Location' });
  await expect(dialog).toBeVisible({ timeout: 5_000 });

  await expect(dialog.getByPlaceholder('e.g. Main Branch')).toBeVisible();
  await expect(dialog.getByPlaceholder('e.g. LOC-001')).toBeVisible();
});

test('creates location and sees it in list', async ({ page }) => {
  const code = `E2E-${Date.now()}`;

  await page.getByRole('button', { name: 'Add Location' }).click();

  const dialog = page.locator('[role="dialog"]').filter({ hasText: 'Add Location' });
  await expect(dialog).toBeVisible({ timeout: 5_000 });

  await dialog.getByPlaceholder('e.g. Main Branch').fill('E2E Test Branch');
  await dialog.getByPlaceholder('e.g. LOC-001').fill(code);
  await dialog.getByPlaceholder('e.g. Lagos').fill('Lagos');

  await dialog.getByRole('button', { name: 'Add Location' }).click();

  await expect(dialog).not.toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('Location created successfully')).toBeVisible({ timeout: 5_000 });

  await expect(page.getByText('E2E Test Branch')).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText(code)).toBeVisible();
});
