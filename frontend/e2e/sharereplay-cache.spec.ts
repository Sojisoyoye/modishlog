import { test, expect } from '@playwright/test';
import { ensureTestUser, loginViaUI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

/**
 * Verifies that shareReplay(1) caching is in place for reference-data services.
 * The first navigation fires the HTTP request; a second navigation to the same
 * page must NOT fire a duplicate request for the same resource.
 */
test.describe('shareReplay caching for reference data', () => {
  test('customers list is not re-fetched on repeat navigation to Sales', async ({ page }) => {
    await loginViaUI(page);

    let customerCallCount = 0;
    page.on('request', (req) => {
      if (req.url().includes('/customers') && req.method() === 'GET' && !req.url().includes('/customers/')) {
        customerCallCount++;
      }
    });

    // First visit to Sales — triggers initial customer load
    await page.goto('/sales');
    await page.waitForLoadState('networkidle');
    const firstCount = customerCallCount;
    expect(firstCount).toBeGreaterThan(0);

    // Navigate away
    await page.goto('/products');
    await page.waitForLoadState('networkidle');

    // Return to Sales — should use cached observable, no new HTTP call
    const countBefore = customerCallCount;
    await page.goto('/sales');
    await page.waitForLoadState('networkidle');

    expect(customerCallCount).toBe(countBefore);
  });

  test('products list is not re-fetched on repeat navigation', async ({ page }) => {
    await loginViaUI(page);

    let productCallCount = 0;
    page.on('request', (req) => {
      if (req.url().includes('/products') && req.method() === 'GET' &&
          !req.url().includes('/products/categories') &&
          !req.url().includes('/products/')) {
        productCallCount++;
      }
    });

    // First visit to Sales — loads all products for the sale form
    await page.goto('/sales');
    await page.waitForLoadState('networkidle');
    const firstCount = productCallCount;
    expect(firstCount).toBeGreaterThan(0);

    // Navigate away
    await page.goto('/inventory');
    await page.waitForLoadState('networkidle');

    // Return — no new product requests
    const countBefore = productCallCount;
    await page.goto('/sales');
    await page.waitForLoadState('networkidle');

    expect(productCallCount).toBe(countBefore);
  });

  test('locations list is not re-fetched on repeat navigation to Sales', async ({ page }) => {
    await loginViaUI(page);

    let locationCallCount = 0;
    page.on('request', (req) => {
      if (req.url().includes('/locations') && req.method() === 'GET' &&
          !req.url().includes('/locations/')) {
        locationCallCount++;
      }
    });

    // First visit to Sales
    await page.goto('/sales');
    await page.waitForLoadState('networkidle');
    expect(locationCallCount).toBeGreaterThan(0);

    // Navigate away then back
    await page.goto('/inventory');
    await page.waitForLoadState('networkidle');
    const countBefore = locationCallCount;
    await page.goto('/sales');
    await page.waitForLoadState('networkidle');

    expect(locationCallCount).toBe(countBefore);
  });

  test('customer cache is busted after creating a new customer', async ({ page }) => {
    await loginViaUI(page);

    let customerCallCount = 0;
    page.on('request', (req) => {
      if (req.url().includes('/customers') && req.method() === 'GET' && !req.url().includes('/customers/')) {
        customerCallCount++;
      }
    });

    // Load Sales (primes the customer cache)
    await page.goto('/sales');
    await page.waitForLoadState('networkidle');
    const afterFirstLoad = customerCallCount;

    // Navigate to Customers page and create a new one (mutates the data → busts cache)
    await page.goto('/customers');
    await page.waitForLoadState('networkidle');
    await page.getByRole('button', { name: 'Add Customer' }).click();
    const name = `Cache Bust ${Date.now()}`;
    await page.getByPlaceholder('Customer name').fill(name);
    await page.getByRole('button', { name: 'Save Customer' }).click();
    await page.getByRole('dialog').waitFor({ state: 'hidden' });

    // After mutation the cache should be invalidated; re-visiting Sales must fire a new request
    const countBeforeReturn = customerCallCount;
    await page.goto('/sales');
    await page.waitForLoadState('networkidle');

    // A fresh request must have fired after the mutation busted the cache
    expect(customerCallCount).toBeGreaterThan(countBeforeReturn);
    expect(customerCallCount).toBeGreaterThan(afterFirstLoad);
  });
});
