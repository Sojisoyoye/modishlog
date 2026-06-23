import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

// ---------------------------------------------------------------------------
// Invoice Schemes E2E Tests (task #122)
// ---------------------------------------------------------------------------
// Note: The backend has no DELETE endpoint for invoice schemes, so afterAll
// cleanup is not possible. Tests use a timestamp-based scheme name to avoid
// row-matching ambiguity across re-runs.
// ---------------------------------------------------------------------------

let schemeName: string;
const INITIAL_PREFIX = 'E2EINV-';
const EDITED_PREFIX = 'E2EINVEDIT-';

test.beforeAll(async () => {
  await ensureTestUser();
  // Unique name per run prevents filter ambiguity when no delete is available
  schemeName = `E2E Blank Scheme ${Date.now()}`;
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/settings/invoice-schemes');
  await expect(page.getByRole('heading', { name: 'Invoice Schemes' })).toBeVisible();
});

// ---------------------------------------------------------------------------
// Existing layout tests
// ---------------------------------------------------------------------------

test('shows heading and Add Scheme button', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Invoice Schemes' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Add Scheme/i })).toBeVisible();
});

test('opens add scheme dialog with type radio buttons', async ({ page }) => {
  await page.getByRole('button', { name: /Add Scheme/i }).click();
  await expect(page.getByText(/blank/i).first()).toBeVisible();
  await expect(page.getByText(/year/i).first()).toBeVisible();
});

// ---------------------------------------------------------------------------
// CRUD flows
// ---------------------------------------------------------------------------

test.describe.configure({ mode: 'serial' });

test.describe('Invoice scheme CRUD', () => {
  test('creates a blank-prefix scheme and it appears in the list', async ({ page }) => {
    await page.getByRole('button', { name: /Add Scheme/i }).click();

    // Dialog must open
    const dialog = page.getByRole('dialog').filter({ hasText: 'Add Scheme' });
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    // Fill name
    await dialog.getByPlaceholder('e.g. Default Invoice').fill(schemeName);

    // Select blank type (default, but be explicit)
    await dialog.locator('input[type="radio"][value="blank"]').check();

    // Fill prefix
    await dialog.getByPlaceholder('e.g. INV-').fill(INITIAL_PREFIX);

    // Submit
    await dialog.getByRole('button', { name: /Create Scheme/i }).click();

    // Success toast
    await expect(page.getByText('Scheme created')).toBeVisible({ timeout: 10_000 });

    // Scheme appears in the list with our prefix
    const schemeRow = page.getByRole('row').filter({ hasText: schemeName });
    await expect(schemeRow).toBeVisible({ timeout: 5_000 });
    await expect(schemeRow).toContainText(INITIAL_PREFIX);

    // Preview column shows correct blank-type format: PREFIX00001
    await expect(schemeRow).toContainText(`${INITIAL_PREFIX}00001`);
  });

  test('edits the scheme prefix and the updated prefix appears in the list', async ({ page }) => {
    // Find the row created in the previous test
    const schemeRow = page.getByRole('row').filter({ hasText: schemeName });
    await expect(schemeRow).toBeVisible({ timeout: 10_000 });

    // Click Edit button on that row
    await schemeRow.getByRole('button', { name: /Edit/i }).click();

    // Edit dialog must open
    const dialog = page.getByRole('dialog').filter({ hasText: 'Edit Scheme' });
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    // Change prefix
    const prefixInput = dialog.getByPlaceholder('e.g. INV-');
    await prefixInput.clear();
    await prefixInput.fill(EDITED_PREFIX);

    // Save
    await dialog.getByRole('button', { name: /Save Changes/i }).click();

    // Success toast
    await expect(page.getByText('Scheme updated')).toBeVisible({ timeout: 10_000 });

    // Row must now show the edited prefix
    const updatedRow = page.getByRole('row').filter({ hasText: schemeName });
    await expect(updatedRow).toContainText(EDITED_PREFIX);
  });

  test('preview column shows the correct invoice format after edit', async ({ page }) => {
    // blank type, prefix=EDITED_PREFIX, digits=5, next_number=1
    // computePreview: EDITED_PREFIX + '00001'
    const schemeRow = page.getByRole('row').filter({ hasText: schemeName });
    await expect(schemeRow).toBeVisible({ timeout: 10_000 });
    await expect(schemeRow).toContainText(`${EDITED_PREFIX}00001`);
  });
});
