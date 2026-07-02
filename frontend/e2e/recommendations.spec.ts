import { test, expect, request as pwRequest } from '@playwright/test';
import { ensureTestUser, loginViaUI, getAPIToken } from './helpers/auth';

const API = 'http://localhost:8000/api/v1';

/**
 * Trigger recommendation generation via API and return the generated IDs.
 * Returns an empty array if generation produces no results (clean environment).
 */
async function seedRecommendations(): Promise<string[]> {
  const token = await getAPIToken();
  const ctx = await pwRequest.newContext();
  try {
    const resp = await ctx.post(`${API}/ai/recommendations/generate`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok()) return [];
    const recs: { id: string }[] = await resp.json();
    return recs.map((r) => r.id);
  } finally {
    await ctx.dispose();
  }
}

/**
 * Fetch the current list of PENDING recommendations via API.
 */
async function getPendingRecs(): Promise<{ id: string; title: string }[]> {
  const token = await getAPIToken();
  const ctx = await pwRequest.newContext();
  try {
    const resp = await ctx.get(`${API}/ai/recommendations`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok()) return [];
    const data: { items: { id: string; title: string; status: string }[] } = await resp.json();
    return data.items.filter((r) => r.status === 'PENDING');
  } finally {
    await ctx.dispose();
  }
}

test.describe('AI Recommendations page', () => {
  test.beforeAll(async () => {
    test.setTimeout(90_000);
    await ensureTestUser();
    // Seed recommendations so apply/dismiss tests have cards to interact with
    await seedRecommendations();
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
    await page.goto('/recommendations');
    await expect(page.getByRole('heading', { name: 'AI Recommendations' })).toBeVisible({ timeout: 15_000 });
  });

  test('page loads with heading, subtitle and action buttons', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'AI Recommendations' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('AI-powered insights to optimize your business')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Generate New' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Show History' })).toBeVisible();
  });

  test('category filter buttons are all present', async ({ page }) => {
    for (const cat of ['All', 'PRICING', 'INVENTORY', 'FX', 'CASHFLOW', 'ORDERS']) {
      await expect(page.getByRole('button', { name: cat, exact: true })).toBeVisible();
    }
  });

  test('Generate New button triggers generation and returns to ready state', async ({ page }) => {
    await page.getByRole('button', { name: 'Generate New' }).click();

    // Spinner shows while generating
    await expect(page.getByText('Generating...')).toBeVisible();

    // Button returns to normal when generation completes — wait up to 45s for AI API
    await expect(page.getByRole('button', { name: 'Generate New' })).toBeVisible({ timeout: 45_000 });
    // Page heading still visible — no navigation error
    await expect(page.getByRole('heading', { name: 'AI Recommendations' })).toBeVisible({ timeout: 15_000 });
  });

  test('Show History / Show Active toggle switches view', async ({ page }) => {
    // Start on active view
    await expect(page.getByRole('button', { name: 'Show History' })).toBeVisible();

    // Toggle to history
    await page.getByRole('button', { name: 'Show History' }).click();
    await expect(page.getByRole('button', { name: 'Show Active' })).toBeVisible({ timeout: 10_000 });

    // Toggle back to active
    await page.getByRole('button', { name: 'Show Active' }).click();
    await expect(page.getByRole('button', { name: 'Show History' })).toBeVisible();
  });

  test('switching tabs does not leave skeleton permanently visible', async ({ page }) => {
    await page.goto('/recommendations');
    // Toggle tabs
    const historyBtn = page.getByRole('button', { name: /history/i }).first();
    if (await historyBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await historyBtn.click();
      await page.waitForTimeout(100);
      const activeBtn = page.getByRole('button', { name: /active/i }).first();
      if (await activeBtn.isVisible()) {
        await activeBtn.click();
        // After clicking Active, skeleton should not persist indefinitely
        await expect(page.locator('.animate-pulse').first()).not.toBeVisible({ timeout: 3000 });
      }
    }
  });

  test.describe('Recommendation card actions', () => {
    test('Apply button removes recommendation from pending list and shows success toast', async ({
      page,
    }) => {
      const pending = await getPendingRecs();
      if (pending.length === 0) {
        test.skip(true, 'No PENDING recommendations available — run generate first');
        return;
      }

      // Wait for cards to render
      await expect(page.locator('[data-testid="rec-card"]').first()).toBeVisible({ timeout: 10_000 });

      // Count initial cards
      const initialCount = await page.locator('[data-testid="rec-card"]').count();
      expect(initialCount).toBeGreaterThan(0);

      // Click Apply on the first card
      const firstApply = page.getByRole('button', { name: 'Apply' }).first();
      await expect(firstApply).toBeVisible();
      await firstApply.click();

      // Success toast appears
      await expect(page.getByText('Applied')).toBeVisible({ timeout: 5000 });

      // Card is removed from the list
      await expect(page.locator('[data-testid="rec-card"]')).toHaveCount(
        initialCount - 1,
        { timeout: 5000 },
      );
    });

    test('Dismiss button opens dialog, requires reason, removes recommendation', async ({
      page,
    }) => {
      const pending = await getPendingRecs();
      if (pending.length === 0) {
        test.skip(true, 'No PENDING recommendations available — run generate first');
        return;
      }

      // Wait for cards to render
      await expect(page.locator('[data-testid="rec-card"]').first()).toBeVisible({ timeout: 10_000 });

      const initialCount = await page.locator('[data-testid="rec-card"]').count();
      expect(initialCount).toBeGreaterThan(0);

      // Click Dismiss on the first card
      const firstDismiss = page.getByRole('button', { name: 'Dismiss' }).first();
      await expect(firstDismiss).toBeVisible();
      await firstDismiss.click();

      // Dismiss dialog opens
      const dialog = page.getByRole('dialog');
      await expect(dialog).toBeVisible();
      await expect(dialog.getByText('Dismiss Recommendation')).toBeVisible();
      await expect(dialog.getByText('Why are you dismissing this recommendation?')).toBeVisible();

      // Dismiss button is disabled until reason is entered
      const confirmBtn = dialog.getByRole('button', { name: 'Dismiss' });
      await expect(confirmBtn).toBeDisabled();

      // Fill in reason
      await dialog.locator('textarea').fill('Not relevant to current business priorities');

      // Button becomes enabled
      await expect(confirmBtn).toBeEnabled();
      await confirmBtn.click();

      // Info toast appears
      await expect(page.getByText('Dismissed')).toBeVisible({ timeout: 5000 });

      // Card is removed from the list
      await expect(page.locator('[data-testid="rec-card"]')).toHaveCount(
        initialCount - 1,
        { timeout: 5000 },
      );
    });
  });
});
