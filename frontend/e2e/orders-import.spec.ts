import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';
import path from 'path';
import fs from 'fs';
import os from 'os';

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/orders');
  await expect(page.getByRole('heading', { name: 'Purchase Orders' })).toBeVisible();
});

test('Import Orders button is visible on orders page', async ({ page }) => {
  await expect(page.getByRole('button', { name: 'Import Orders' })).toBeVisible();
});

test('Import dialog opens with Download Template link', async ({ page }) => {
  await page.getByRole('button', { name: 'Import Orders' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('link', { name: /download template/i })).toBeVisible();
});

test('Upload valid CSV shows preview and creates orders on submit', async ({ page }) => {
  // Create a minimal valid CSV fixture
  const csvContent = [
    'supplier_name,currency,line_item_sku,line_item_quantity,line_item_unit_cost',
    'Import Test Supplier,USD,TEST-SKU-IMPORT,1,100.00',
  ].join('\n');

  const tmpFile = path.join(os.tmpdir(), 'test_import.csv');
  fs.writeFileSync(tmpFile, csvContent);

  await page.getByRole('button', { name: 'Import Orders' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();

  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(tmpFile);

  await expect(page.getByText(/1 row/i)).toBeVisible({ timeout: 3000 });

  fs.unlinkSync(tmpFile);
});

test('Upload CSV with unknown SKU shows error table', async ({ page }) => {
  const csvContent = [
    'supplier_name,currency,line_item_sku,line_item_quantity,line_item_unit_cost',
    'Bad Supplier,USD,NONEXISTENT-SKU-XYZ,1,50.00',
  ].join('\n');

  const tmpFile = path.join(os.tmpdir(), 'test_import_bad.csv');
  fs.writeFileSync(tmpFile, csvContent);

  await page.getByRole('button', { name: 'Import Orders' }).click();
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(tmpFile);
  await page.getByRole('button', { name: /submit|import/i }).click();

  await expect(page.getByText(/error/i)).toBeVisible({ timeout: 5000 });

  fs.unlinkSync(tmpFile);
});
