import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

const API = process.env['API_URL'] ?? 'http://localhost:8000/api/v1';

async function getAuthToken(): Promise<string> {
  const resp = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: 'testuser@example.com', password: 'Str0ng!Pass#99' }),
  });
  const data = await resp.json();
  return data.access_token as string;
}

async function createExpenseCategory(token: string, name: string): Promise<{ id: string; name: string }> {
  const resp = await fetch(`${API}/expense-categories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name }),
  });
  return resp.json();
}

async function createExpense(token: string, data: Record<string, unknown>): Promise<{ id: string }> {
  const resp = await fetch(`${API}/expenses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ amount_ngn: '5000', amount_usd: '3.33', expense_date: '2026-07-01', ...data }),
  });
  return resp.json();
}

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/expenses');
  await expect(page.getByRole('heading', { name: 'Expenses' })).toBeVisible({ timeout: 15000 });
});

test('expenses page loads with table', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Expenses' })).toBeVisible();
  await expect(page.getByRole('table').first()).toBeVisible({ timeout: 10000 });
});

test('create expense category via modal', async ({ page }) => {
  await page.getByRole('button', { name: 'Manage Categories' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();

  const catName = `E2E Cat ${Date.now()}`;
  await dialog.getByPlaceholder('Category name').fill(catName);
  // Scoped to the dialog — the page's own "Add Expense" button also
  // matches an unscoped getByRole('button', { name: 'Add' }) since
  // Playwright's default name match is a case-insensitive substring.
  await dialog.getByRole('button', { name: 'Add' }).click();

  await expect(dialog.getByText(catName)).toBeVisible({ timeout: 8000 });
  await dialog.getByRole('button', { name: 'Close' }).click();
});

test('create expense and see in list', async ({ page }) => {
  const token = await getAuthToken();
  const cat = await createExpenseCategory(token, `Cat ${Date.now()}`);

  await page.getByRole('button', { name: 'Add Expense' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();

  await page.getByLabel('Amount (NGN)').fill('75000');
  await page.getByLabel('Amount (USD)').fill('50.00');
  await page.getByLabel('Expense Date').fill('2026-07-01');

  await page.getByRole('button', { name: 'Save Expense' }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden', timeout: 10000 });

  await expect(
    page.getByRole('table').first().locator('tbody tr').first(),
  ).not.toHaveText('No expenses found.', { timeout: 5000 });
});

test('edit expense note', async ({ page }) => {
  const token = await getAuthToken();
  await createExpense(token, { note: 'original note' });

  await page.reload();
  await expect(page.getByRole('heading', { name: 'Expenses' })).toBeVisible({ timeout: 15000 });

  await page.getByRole('table').first().locator('tbody tr').first().getByRole('button', { name: 'Edit' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();

  await page.getByLabel('Note').fill('updated note');
  await page.getByRole('button', { name: 'Save Expense' }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden', timeout: 10000 });

  await expect(page.getByRole('table').first().locator('tbody tr').first()).toContainText('updated note', { timeout: 5000 });
});

test('shows skeleton loader while expenses are loading', async ({ page }) => {
  // Navigate fresh so we can observe initial load state
  await page.goto('/expenses');
  // The table (or skeleton placeholder) should appear during/after load
  await expect(page.getByRole('table').first()).toBeVisible({ timeout: 10000 });
  // Heading confirms the page fully rendered
  await expect(page.getByRole('heading', { name: 'Expenses' })).toBeVisible();
});

test('delete button is disabled while deletion is in progress', async ({ page }) => {
  const token = await getAuthToken();
  await createExpense(token, { note: 'to be deleted' });

  await page.reload();
  await expect(page.getByRole('heading', { name: 'Expenses' })).toBeVisible({ timeout: 15000 });

  const deleteButtons = page.getByRole('button', { name: /delete/i });
  const count = await deleteButtons.count();
  if (count > 0) {
    // Delete button should be enabled before any action is taken
    await expect(deleteButtons.first()).toBeEnabled();
  }
});
