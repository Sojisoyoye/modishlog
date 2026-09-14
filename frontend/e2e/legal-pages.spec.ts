import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaAPI } from './helpers/auth';

// ---------------------------------------------------------------------------
// Legal pages E2E tests (task 234)
// ---------------------------------------------------------------------------

test.describe('Terms of Service page', () => {
  test('loads directly and shows the heading', async ({ page }) => {
    await page.goto('/terms');
    await expect(page.getByRole('heading', { name: 'Terms of Service', exact: true })).toBeVisible();
  });

  test('mouse-wheel scroll actually moves the page', async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 600 });
    await page.goto('/terms');
    const container = page.getByTestId('legal-page-scroll-container');
    await page.mouse.move(400, 300);
    await page.mouse.wheel(0, 2000);
    await expect.poll(() => container.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
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

test.describe('Privacy Policy page', () => {
  test('mouse-wheel scroll actually moves the page', async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 600 });
    await page.goto('/privacy');
    const container = page.getByTestId('legal-page-scroll-container');
    await page.mouse.move(400, 300);
    await page.mouse.wheel(0, 2000);
    await expect.poll(() => container.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  });
});

test.describe('Landing page footer links to both legal pages', () => {
  test('footer Privacy and Terms links point to the real pages', async ({ page }) => {
    await page.goto('/');
    const privacyLink = page.getByRole('link', { name: 'Privacy', exact: true });
    const termsLink = page.getByRole('link', { name: 'Terms', exact: true });
    await expect(privacyLink).toHaveAttribute('href', '/privacy');
    await expect(termsLink).toHaveAttribute('href', '/terms');
  });

  test('clicking footer Terms navigates to the Terms of Service page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Terms', exact: true }).click();
    await expect(page).toHaveURL(/\/terms$/);
    await expect(page.getByRole('heading', { name: 'Terms of Service', exact: true })).toBeVisible();
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

test.describe('Sidebar footer links to legal pages for logged-in users', () => {
  test.beforeAll(async () => {
    await ensureTestUser();
  });

  test.beforeEach(async ({ page }) => {
    await loginViaAPI(page);
  });

  test('sidebar shows Terms and Privacy links', async ({ page }) => {
    const termsLink = page.getByRole('link', { name: 'Terms', exact: true });
    const privacyLink = page.getByRole('link', { name: 'Privacy', exact: true });
    await expect(termsLink).toHaveAttribute('href', '/terms');
    await expect(privacyLink).toHaveAttribute('href', '/privacy');
  });

  test('clicking Terms in the sidebar navigates to the Terms of Service page', async ({ page }) => {
    await page.getByRole('link', { name: 'Terms', exact: true }).click();
    await expect(page).toHaveURL(/\/terms$/);
    await expect(page.getByRole('heading', { name: 'Terms of Service', exact: true })).toBeVisible();
  });
});
