import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Legal pages E2E tests (task 234)
// ---------------------------------------------------------------------------

test.describe('Terms of Service page', () => {
  test('loads directly and shows the heading', async ({ page }) => {
    await page.goto('/terms');
    await expect(page.getByRole('heading', { name: 'Terms of Service', exact: true })).toBeVisible();
  });

  test('"Back to ModishLog" link returns to /', async ({ page }) => {
    await page.goto('/terms');
    await page.getByText('Back to ModishLog').click();
    await expect(page).toHaveURL(/\/(login)?$/);
  });

  test('links to the Privacy Policy', async ({ page }) => {
    await page.goto('/terms');
    await expect(page.getByRole('link', { name: 'Privacy Policy' }).first()).toHaveAttribute('href', /\/privacy/);
  });
});

test.describe('Register page links to both legal pages', () => {
  test('consent checkbox links to Terms of Service and Privacy Policy', async ({ page }) => {
    await page.goto('/register');
    const termsLink = page.getByRole('link', { name: 'Terms of Service' });
    const privacyLink = page.getByRole('link', { name: 'Privacy Policy' });
    await expect(termsLink).toHaveAttribute('href', '/terms');
    await expect(privacyLink).toHaveAttribute('href', '/privacy');
  });
});
