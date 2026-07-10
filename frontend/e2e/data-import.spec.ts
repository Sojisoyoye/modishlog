import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import os from 'os';
import { ensureTestUser, loginViaUI } from './helpers/auth';

function writeTmpCsv(name: string, rows: string[]): string {
  const tmpFile = path.join(os.tmpdir(), name);
  fs.writeFileSync(tmpFile, rows.join('\n'));
  return tmpFile;
}

const PRODUCTS_CSV = [
  'source_id,name,sku,barcode,unit_cost,selling_price,currency,category_source_id,is_active',
  'P1,Ankara Print Fabric,AFK-001,,4500,7000,NGN,,true',
  'P2,White Lace (per yard),WL-003,,1200,2000,NGN,,true',
];

const CUSTOMERS_CSV = [
  'source_id,name,email,contact_number',
  'C1,Adaeze Okonkwo,adaeze@example.com,+2348012345678',
];

const BAD_PRODUCTS_CSV = [
  'source_id,name,sku,barcode,unit_cost,selling_price,currency,category_source_id,is_active',
  'P1,,AFK-001,,4500,7000,NGN,,true', // missing required "name"
];

/** Drives the wizard through source + method selection, landing on the CSV upload step. */
async function goToCsvUploadStep(page: import('@playwright/test').Page, sourceLabel = 'Generic CSV') {
  await page.getByRole('button', { name: 'Start New Import' }).click();
  await expect(page.getByRole('heading', { name: /choose your source/i })).toBeVisible();
  await page.getByRole('button', { name: new RegExp(sourceLabel, 'i') }).click();
  await page.getByRole('button', { name: 'Next' }).click();

  await expect(page.getByRole('heading', { name: /how do you want to import/i })).toBeVisible();
  await page.getByRole('button', { name: /Upload CSV files/i }).click();
  await page.getByRole('button', { name: 'Next' }).click();

  await expect(page.getByRole('heading', { name: /download templates/i })).toBeVisible();
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByRole('heading', { name: /upload your files/i })).toBeVisible();
}

test.beforeAll(async () => {
  await ensureTestUser();
});

test.beforeEach(async ({ page }) => {
  await loginViaUI(page);
  await page.goto('/settings/import');
  await expect(page.getByRole('heading', { name: 'Data Imports' })).toBeVisible({ timeout: 15_000 });
});

test('import history page shows Start New Import button', async ({ page }) => {
  await expect(page.getByRole('button', { name: 'Start New Import' })).toBeVisible();
});

test('wizard: selecting a source system and CSV method reaches templates step', async ({ page }) => {
  await page.getByRole('button', { name: 'Start New Import' }).click();
  await expect(page.getByRole('heading', { name: /choose your source/i })).toBeVisible();

  await page.getByRole('button', { name: /Generic CSV/i }).click();
  await page.getByRole('button', { name: 'Next' }).click();

  await expect(page.getByRole('heading', { name: /how do you want to import/i })).toBeVisible();
  await page.getByRole('button', { name: /Upload CSV files/i }).click();
  await page.getByRole('button', { name: 'Next' }).click();

  await expect(page.getByRole('heading', { name: /download templates/i })).toBeVisible();
  await expect(page.getByRole('link', { name: /download all templates/i })).toBeVisible();
});

test('wizard: Shopify source shows Shopify-specific export instructions', async ({ page }) => {
  await page.getByRole('button', { name: 'Start New Import' }).click();
  await page.getByRole('button', { name: /Shopify/i }).click();
  await page.getByRole('button', { name: 'Next' }).click();
  await page.getByRole('button', { name: /Upload CSV files/i }).click();
  await page.getByRole('button', { name: 'Next' }).click();

  await expect(page.getByText(/shopify.*products and orders csv export/i)).toBeVisible();
});

test('wizard: upload valid CSVs then validate shows correct row counts with no errors', async ({ page }) => {
  const productsFile = writeTmpCsv('import_products.csv', PRODUCTS_CSV);
  const customersFile = writeTmpCsv('import_customers.csv', CUSTOMERS_CSV);

  await goToCsvUploadStep(page);
  await page.locator('input[type="file"]#file-products').setInputFiles(productsFile);
  await page.locator('input[type="file"]#file-customers').setInputFiles(customersFile);
  await page.getByRole('button', { name: 'Next' }).click();

  await expect(page.getByRole('heading', { name: /validating/i })).toBeVisible();
  await expect(page.getByText(/2 records/i)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/1 record/i)).toBeVisible();
  await expect(page.getByText(/0 errors, 0 warnings/i)).toBeVisible();

  fs.unlinkSync(productsFile);
  fs.unlinkSync(customersFile);
});

test('wizard: uploading a CSV with a missing required field shows a blocking error', async ({ page }) => {
  const badFile = writeTmpCsv('import_bad_products.csv', BAD_PRODUCTS_CSV);

  await goToCsvUploadStep(page);
  await page.locator('input[type="file"]#file-products').setInputFiles(badFile);
  await page.getByRole('button', { name: 'Next' }).click();

  await expect(page.getByText(/name is required/i)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('button', { name: 'Fix & Re-upload' })).toBeVisible();
  await expect(page.getByRole('button', { name: /proceed to import/i })).toHaveCount(0);

  fs.unlinkSync(badFile);
});

test('wizard: full happy path — upload, validate, confirm, summary shows correct counts', async ({ page }) => {
  const productsFile = writeTmpCsv('import_happy_products.csv', PRODUCTS_CSV);

  await goToCsvUploadStep(page);
  await page.locator('input[type="file"]#file-products').setInputFiles(productsFile);
  await page.getByRole('button', { name: 'Next' }).click();

  await expect(page.getByText(/0 errors, 0 warnings/i)).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: /looks good.*proceed to import/i }).click();

  // Mandatory confirmation screen (subtask 163.2)
  await expect(page.getByRole('heading', { name: /review your import/i })).toBeVisible();
  await expect(page.getByText(/2 records/i).first()).toBeVisible();
  await page.getByRole('button', { name: /yes, import this data/i }).click();

  await expect(page.getByRole('heading', { name: /import complete/i })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/2 products imported/i)).toBeVisible();

  fs.unlinkSync(productsFile);
});

test('wizard: cancel at confirmation screen does not import any data', async ({ page }) => {
  const productsFile = writeTmpCsv('import_cancel_products.csv', PRODUCTS_CSV);

  await goToCsvUploadStep(page);
  await page.locator('input[type="file"]#file-products').setInputFiles(productsFile);
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByText(/0 errors, 0 warnings/i)).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: /looks good.*proceed to import/i }).click();

  await expect(page.getByRole('heading', { name: /review your import/i })).toBeVisible();
  await page.getByRole('button', { name: /cancel.*don't import/i }).click();

  await expect(page.getByText(/import cancelled/i)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Data Imports' })).toBeVisible();

  fs.unlinkSync(productsFile);
});

test('undo a completed import removes it from active data and updates history', async ({ page }) => {
  const productsFile = writeTmpCsv('import_undo_products.csv', PRODUCTS_CSV);

  await goToCsvUploadStep(page);
  await page.locator('input[type="file"]#file-products').setInputFiles(productsFile);
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByText(/0 errors, 0 warnings/i)).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: /looks good.*proceed to import/i }).click();
  await page.getByRole('button', { name: /yes, import this data/i }).click();
  await expect(page.getByRole('heading', { name: /import complete/i })).toBeVisible({ timeout: 20_000 });

  page.once('dialog', (d) => d.accept());
  await page.getByRole('button', { name: /undo this import/i }).click();

  await expect(page.getByText(/import undone/i)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('heading', { name: 'Data Imports' })).toBeVisible();
  await expect(page.getByText(/rolled back/i).first()).toBeVisible();

  fs.unlinkSync(productsFile);
});
