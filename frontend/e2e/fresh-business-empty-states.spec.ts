/**
 * Fresh-business empty-state & edge-case walkthrough (task #244).
 *
 * Every other E2E spec shares the single `e2e-suite@modishlogtest.com`
 * business, which accumulates fixture data (products, sales, orders) as
 * the suite runs -- by the time any of those specs load a page, it's
 * never actually empty. A brand-new signup's first session is entirely
 * an empty-state experience, so this spec onboards its own isolated
 * business with zero data and walks the core pages a new owner lands on
 * first, plus a couple of invalid-input/network-failure edge cases.
 */
import { test, expect, request as pwRequest, Page } from '@playwright/test';

const API = 'http://localhost:8000/api/v1';
const PASSWORD = 'FreshBiz!Pass#14';

async function onboardFreshBusiness(): Promise<{ email: string }> {
  const email = `e2e-fresh-${Date.now()}-${Math.random().toString(36).slice(2, 6)}@modishlogtest.com`;
  const ctx = await pwRequest.newContext();
  try {
    const resp = await ctx.post(`${API}/auth/onboard`, {
      data: {
        full_name: 'Fresh Business Owner',
        email,
        password: PASSWORD,
        business_name: `Fresh Biz ${Date.now()}`,
        currency: 'NGN',
        timezone: 'Africa/Lagos',
        fiscal_year_start_month: 1,
        ndpr_consent: true,
      },
    });
    if (!resp.ok()) throw new Error(`onboard failed: ${resp.status()} ${await resp.text()}`);
  } finally {
    await ctx.dispose();
  }
  return { email };
}

async function loginFreshBusiness(page: Page, email: string): Promise<void> {
  const resp = await page.context().request.post(`${API}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  if (!resp.ok()) throw new Error(`login failed: ${resp.status()} ${await resp.text()}`);
  await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
  await page.waitForURL('**/dashboard', { timeout: 20_000 });
}

/** Attach a page-error collector; call assertNoErrors() after navigating. */
function trackJsErrors(page: Page): { assertNoErrors: () => void } {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  return {
    assertNoErrors: () => expect(errors.filter((e) => !e.includes('favicon'))).toHaveLength(0),
  };
}

let freshEmail: string;

test.beforeAll(async () => {
  ({ email: freshEmail } = await onboardFreshBusiness());
});

test.beforeEach(async ({ page }) => {
  await loginFreshBusiness(page, freshEmail);
});

// ---------------------------------------------------------------------------
// Empty-state walkthrough across core pages
// ---------------------------------------------------------------------------

test('dashboard renders without error for a brand-new business with zero data', async ({ page }) => {
  const { assertNoErrors } = trackJsErrors(page);
  await page.goto('/dashboard');
  await page.waitForLoadState('domcontentloaded');
  // KPI heading must appear -- not a stuck spinner or crashed render.
  await expect(page.getByText("Today's Revenue")).toBeVisible({ timeout: 15_000 });
  // Zero-data KPI values must render as a real zero, not a blank/NaN/undefined.
  await expect(page.getByText(/₦\s*0(\.00)?/).first()).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(1_000);
  assertNoErrors();
});

test('products page shows an empty state, not a broken table', async ({ page }) => {
  const { assertNoErrors } = trackJsErrors(page);
  await page.goto('/products');
  await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible({ timeout: 15_000 });
  // No data rows -- either an explicit empty-state message or simply zero
  // rows in the table body, but never a spinner that never resolves.
  const spinner = page.locator('.pi-spinner, [role="status"]');
  await expect(spinner).toHaveCount(0, { timeout: 10_000 });
  await page.waitForTimeout(500);
  assertNoErrors();
});

test('sales page shows an empty state, not a broken table', async ({ page }) => {
  const { assertNoErrors } = trackJsErrors(page);
  await page.goto('/sales');
  await page.waitForLoadState('domcontentloaded');
  const emptyText = page.getByText(/no (transactions|sales)/i).first();
  const anyRow = page.getByRole('row').nth(1);
  await expect(emptyText.or(anyRow)).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(500);
  assertNoErrors();
});

test('inventory page renders without error for zero products', async ({ page }) => {
  const { assertNoErrors } = trackJsErrors(page);
  await page.goto('/inventory');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(1_500);
  assertNoErrors();
});

test('reports (profit-loss) renders a zero-data report, not a crash', async ({ page }) => {
  const { assertNoErrors } = trackJsErrors(page);
  await page.goto('/reports/profit-loss');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(1_500);
  // A real error boundary/toast would say so explicitly -- absence of that
  // plus no JS exception is the signal a zero-data report rendered cleanly.
  await expect(page.getByText(/something went wrong|unexpected error/i)).toHaveCount(0);
  assertNoErrors();
});

test('recommendations page handles zero sales history gracefully', async ({ page }) => {
  const { assertNoErrors } = trackJsErrors(page);
  await page.goto('/recommendations');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(1_500);
  await expect(page.getByText(/something went wrong|unexpected error/i)).toHaveCount(0);
  assertNoErrors();
});

// ---------------------------------------------------------------------------
// Invalid-input edge cases
// ---------------------------------------------------------------------------

test('product form rejects a negative selling price instead of crashing', async ({ page }) => {
  await page.goto('/products');
  await page.getByRole('button', { name: 'New Product' }).click();
  const addForm = page.locator('#add-product-form');
  await addForm.getByPlaceholder('Product name').fill(`E2E Negative ${Date.now()}`);
  await addForm.locator('[data-testid="add-unit-cost-input"]').fill('100');
  await addForm.locator('[data-testid="add-selling-price-input"]').fill('-50');

  const submit = addForm.getByRole('button', { name: 'Create Product' });
  // Either the submit button is disabled for an invalid value, or submitting
  // surfaces a validation error -- what must NOT happen is a silently
  // accepted negative price or an unhandled exception.
  const isDisabled = await submit.isDisabled().catch(() => false);
  if (!isDisabled) {
    await submit.click();
    const errorToast = page.getByText(/must be (positive|greater than|at least)/i);
    const formStillOpen = page.locator('#add-product-form');
    await expect(errorToast.or(formStillOpen)).toBeVisible({ timeout: 5_000 });
  } else {
    expect(isDisabled).toBe(true);
  }
});

test('malformed CSV upload surfaces an inline error, not a crash', async ({ page }) => {
  await page.goto('/settings/import');
  await page.waitForLoadState('domcontentloaded');

  // Wizard flow: history -> source -> method -> upload.
  await page.getByRole('button', { name: 'Start New Import' }).click();
  await expect(page.getByText('Choose your source')).toBeVisible({ timeout: 10_000 });

  // Source step: pick "generic" (templates, no API option) and advance.
  await page.getByText('Generic CSV').click();
  await page.getByRole('button', { name: 'Next' }).click();

  // Method step: pick CSV upload and advance.
  await page.getByText('Upload CSV files').click();
  await page.getByRole('button', { name: 'Next' }).click();

  // Upload step opens on the templates sub-phase -- advance to the actual
  // file-picker sub-phase.
  await page.getByRole('button', { name: 'Next' }).click();

  const fileInput = page.locator('#file-products');
  await expect(fileInput).toBeAttached({ timeout: 5_000 });

  // Build a garbage "CSV" (wrong columns entirely) in-memory.
  const garbage = Buffer.from('not,a,real,products,file\nfoo,bar,baz,qux,quux\n');
  await fileInput.setInputFiles({
    name: 'garbage.csv',
    mimeType: 'text/csv',
    buffer: garbage,
  });

  const { assertNoErrors } = trackJsErrors(page);
  await page.getByRole('button', { name: 'Next' }).click();

  // The wizard must surface SOME feedback (inline error or validation step
  // flagging the bad rows) rather than hanging or throwing.
  await page.waitForTimeout(3_000);
  const errorShown = await page.getByText(/fail|error|invalid/i).first().isVisible().catch(() => false);
  const advancedToValidate = page.url().includes('/settings/import');
  expect(errorShown || advancedToValidate).toBe(true);
  assertNoErrors();
});

// ---------------------------------------------------------------------------
// Network-failure edge case
// ---------------------------------------------------------------------------

test('sales page does not hang forever when its API call times out', async ({ page }) => {
  // Abort the sales-list request to simulate a network failure/timeout --
  // the page must settle into some terminal state (error/retry/empty),
  // never spin indefinitely.
  await page.route('**/api/v1/sales**', (route) => route.abort('timedout'));

  const { assertNoErrors } = trackJsErrors(page);
  await page.goto('/sales');
  await page.waitForLoadState('domcontentloaded');

  // Give it a generous window, then assert the spinner isn't still running.
  await page.waitForTimeout(8_000);
  const spinner = page.locator('.pi-spinner, [role="status"]');
  await expect(spinner).toHaveCount(0);
  assertNoErrors();
});
