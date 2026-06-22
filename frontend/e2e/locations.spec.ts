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
  await dialog.getByPlaceholder('e.g. Lagos', { exact: true }).fill('Lagos');

  await dialog.getByRole('button', { name: 'Add Location' }).click();

  await expect(dialog).not.toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('Location created successfully')).toBeVisible({ timeout: 5_000 });

  await expect(page.getByText('E2E Test Branch')).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText(code)).toBeVisible();
});

// ---------------------------------------------------------------------------
// Edit and duplicate-code validation (task #124)
// ---------------------------------------------------------------------------

test.describe('Location edit and duplicate-code validation', () => {
  test('editing a location updates its city in the list', async ({ page }) => {
    const code = `E2E-EDIT-${Date.now()}`;

    // Create the location to edit
    await page.getByRole('button', { name: 'Add Location' }).click();
    const addDialog = page.locator('[role="dialog"]').filter({ hasText: 'Add Location' });
    await expect(addDialog).toBeVisible({ timeout: 5_000 });
    await addDialog.getByPlaceholder('e.g. Main Branch').fill('E2E Edit Branch');
    await addDialog.getByPlaceholder('e.g. LOC-001').fill(code);
    await addDialog.getByPlaceholder('e.g. Lagos', { exact: true }).fill('Abuja');
    await addDialog.getByRole('button', { name: 'Add Location' }).click();
    await expect(addDialog).not.toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('Location created successfully')).toBeVisible({ timeout: 5_000 });

    // Find the row and click the Edit location button
    const row = page.getByRole('row').filter({ hasText: 'E2E Edit Branch' });
    await expect(row).toBeVisible({ timeout: 5_000 });
    await row.getByTitle('Edit location').click();

    // Edit dialog opens
    const editDialog = page.locator('[role="dialog"]').filter({ hasText: 'Edit Location' });
    await expect(editDialog).toBeVisible({ timeout: 5_000 });

    // Change city
    const cityInput = editDialog.getByPlaceholder('e.g. Lagos', { exact: true });
    await cityInput.clear();
    await cityInput.fill('Lagos Updated');

    // Save
    await editDialog.getByRole('button', { name: 'Save Changes' }).click();

    // Success toast
    await expect(page.getByText('Location updated successfully')).toBeVisible({ timeout: 10_000 });

    // Updated city appears in the list row
    const updatedRow = page.getByRole('row').filter({ hasText: 'E2E Edit Branch' });
    await expect(updatedRow).toContainText('Lagos Updated');
  });

  test('creating a location with a duplicate code shows a validation error', async ({ page }) => {
    const ts = Date.now();
    const code = `E2E-DUP-${ts}`;

    // Create the first location with the code
    await page.getByRole('button', { name: 'Add Location' }).click();
    const dialog1 = page.locator('[role="dialog"]').filter({ hasText: 'Add Location' });
    await expect(dialog1).toBeVisible({ timeout: 5_000 });
    await dialog1.getByPlaceholder('e.g. Main Branch').fill(`E2E Dup First ${ts}`);
    await dialog1.getByPlaceholder('e.g. LOC-001').fill(code);
    await dialog1.getByRole('button', { name: 'Add Location' }).click();
    await expect(dialog1).not.toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('Location created successfully')).toBeVisible({ timeout: 5_000 });

    // Try to create another location with the same code
    await page.getByRole('button', { name: 'Add Location' }).click();
    const dialog2 = page.locator('[role="dialog"]').filter({ hasText: 'Add Location' });
    await expect(dialog2).toBeVisible({ timeout: 5_000 });
    await dialog2.getByPlaceholder('e.g. Main Branch').fill(`E2E Dup Second ${ts}`);
    await dialog2.getByPlaceholder('e.g. LOC-001').fill(code);
    await dialog2.getByRole('button', { name: 'Add Location' }).click();

    // Backend returns 409 with "Location code already exists: {code}"
    // Frontend shows it as an error toast detail
    await expect(page.getByText(/Location code already exists/i)).toBeVisible({ timeout: 10_000 });

    // Dialog must remain open (not closed on error)
    await expect(dialog2).toBeVisible();
  });
});
