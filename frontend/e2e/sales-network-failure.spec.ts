import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaAPI } from './helpers/auth';
import { ensureProduct, addStock } from './helpers/data';

// ---------------------------------------------------------------------------
// Task #248 — ModishLog has zero offline-first sync; a connection dropping
// mid-submit must surface a clear error, not hang silently or pretend the
// sale saved. route.abort('failed') simulates a genuinely dropped
// connection (not just an HTTP error status) on the core sales-recording
// flow, closest to what devtools network throttling/offline does. Own file
// (not appended to sales.spec.ts) so the route is registered before this
// test's own navigation, matching cashflow-error-states.spec.ts's rationale.
// ---------------------------------------------------------------------------

test.describe('Sales — dropped connection during submit', () => {
  test('shows a clear error and re-enables the form, not a silent hang', async ({ page }) => {
    await ensureTestUser();
    const product = await ensureProduct('E2E Network Failure Product');
    await addStock(product.id, 20);

    await page.route('**/api/v1/sales/daily-entry', (route) => route.abort('failed'));

    await loginViaAPI(page);
    await page.goto('/sales');
    await expect(page.getByRole('heading', { name: 'Sales', exact: true })).toBeVisible({ timeout: 10_000 });
    await page.getByTestId('tab-record-sales').click();

    const productSelect = page.locator('select').filter({ hasText: 'Select product' }).first();
    await expect(productSelect).toBeVisible({ timeout: 15_000 });
    await expect(productSelect.locator('option').nth(1)).toBeAttached({ timeout: 10_000 });
    await productSelect.selectOption({ label: product.name });
    await page.locator('input[type="number"]').first().fill('2');

    const submitButton = page.getByRole('button', { name: 'Record Sales' }).last();
    await submitButton.click();

    // A clear, visible error -- not a hang, not a false "success" toast.
    await expect(page.getByText('Failed to record sales')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('Sales recorded successfully')).not.toBeVisible();

    // The form must recover, not stay stuck disabled/"submitting" forever.
    await expect(submitButton).toBeEnabled({ timeout: 5_000 });
  });
});
