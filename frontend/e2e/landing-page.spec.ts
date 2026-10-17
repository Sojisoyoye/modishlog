import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

// ---------------------------------------------------------------------------
// Public landing page (task #269) -- pricing section rewrite (Basic/Pro/Scale
// monthly subscription, replacing the old one-time-payment Starter/Growth/
// Scale copy) and an auth-aware header/hero CTA.
// ---------------------------------------------------------------------------

test.describe('Landing page', () => {
  test('logged-out visitor sees Get Started / Login, not Go to Dashboard', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: /get started/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /^login$/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /go to dashboard/i })).toHaveCount(0);
  });

  test('logged-in visitor sees Go to Dashboard instead of Get Started / Login', async ({ page }) => {
    await ensureTestUser();
    await loginViaUI(page);

    await page.goto('/');
    await expect(page.getByRole('link', { name: /go to dashboard/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /get started/i })).toHaveCount(0);

    await page.getByRole('link', { name: /go to dashboard/i }).first().click();
    await page.waitForURL('**/dashboard', { timeout: 20_000 });
  });

  test('pricing section shows the real 3-tier monthly subscription, no one-time-payment language', async ({
    page,
  }) => {
    await page.goto('/');
    const pricing = page.locator('#pricing');

    await expect(pricing.getByText('Basic', { exact: true })).toBeVisible();
    await expect(pricing.getByText('Pro', { exact: true })).toBeVisible();
    await expect(pricing.getByText('Scale', { exact: true })).toBeVisible();
    await expect(pricing.getByText('₦10,000')).toBeVisible();
    await expect(pricing.getByText('₦20,000')).toBeVisible();
    await expect(pricing.getByText('₦45,000')).toBeVisible();

    await expect(page.getByText(/one-time payment/i)).toHaveCount(0);
    await expect(page.getByText(/no monthly fees\. no subscriptions/i)).toHaveCount(0);
  });
});
