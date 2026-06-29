import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/settings');
});

test.describe('Settings — Fiscal Year Start', () => {
  test('fiscal year section is visible on settings page', async ({ page }) => {
    await expect(page.getByText('Fiscal Year', { exact: true })).toBeVisible();
    await expect(page.locator('#fy-month')).toBeVisible();
  });

  test('can save fiscal year start (April 1) and see success message', async ({ page }) => {
    await page.locator('#fy-month').selectOption('4');
    await page.locator('#fy-day').fill('1');
    await page.getByRole('button', { name: 'Save Fiscal Year' }).click();
    await expect(page.getByText('Fiscal year start saved')).toBeVisible({ timeout: 10_000 });
  });

  test('saved fiscal year values are shown after page reload', async ({ page }) => {
    await page.locator('#fy-month').selectOption('4');
    await page.locator('#fy-day').fill('1');
    await page.getByRole('button', { name: 'Save Fiscal Year' }).click();
    await expect(page.getByText('Fiscal year start saved')).toBeVisible({ timeout: 10_000 });

    await page.reload();

    await expect(page.locator('#fy-month')).toHaveValue('4', { timeout: 10_000 });
    await expect(page.locator('#fy-day')).toHaveValue('1');
  });

  test('can clear fiscal year setting by selecting Not configured', async ({ page }) => {
    // Ensure something is saved first
    await page.locator('#fy-month').selectOption('4');
    await page.locator('#fy-day').fill('1');
    await page.getByRole('button', { name: 'Save Fiscal Year' }).click();
    await expect(page.getByText('Fiscal year start saved')).toBeVisible({ timeout: 10_000 });

    // Clear it
    await page.locator('#fy-month').selectOption('');
    await page.getByRole('button', { name: 'Save Fiscal Year' }).click();
    await expect(page.getByText('Fiscal year start saved')).toBeVisible({ timeout: 10_000 });
  });

  test('day input is disabled when no month is selected', async ({ page }) => {
    await page.locator('#fy-month').selectOption('');
    await expect(page.locator('#fy-day')).toBeDisabled();
  });

  test('day input is enabled when a month is selected', async ({ page }) => {
    await page.locator('#fy-month').selectOption('3');
    await expect(page.locator('#fy-day')).toBeEnabled();
  });
});
