import { test, expect, Page } from '@playwright/test';
import { ensureTestUser, loginViaAPI } from './helpers/auth';

test.beforeAll(async () => {
  await ensureTestUser();
});

/**
 * Navigate via an in-app sidebar link (client-side Angular routing) instead of
 * page.goto(), which always forces a full browser navigation. A full
 * navigation tears down and recreates the whole app -- including every
 * `providedIn: 'root'` service and its in-memory shareReplay cache -- so it
 * can never actually exercise (or catch a regression in) cross-navigation
 * caching. Only the very first visit in each test uses page.goto(), as a
 * deliberate cold start.
 */
async function navigateViaSidebar(page: Page, linkName: string): Promise<void> {
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: linkName }).click();
  await page.waitForLoadState('networkidle');
}

/**
 * Verifies that shareReplay(1) caching is in place for reference-data services.
 * The first navigation fires the HTTP request; a second navigation to the same
 * page must NOT fire a duplicate request for the same resource.
 */
test.describe('shareReplay caching for reference data', () => {
  test('customers list is not re-fetched on repeat navigation to Sales', async ({ page }) => {
    await loginViaAPI(page);

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

    // Navigate away (client-side)
    await navigateViaSidebar(page, 'Products');

    // Return to Sales (client-side) — should use cached observable, no new HTTP call
    const countBefore = customerCallCount;
    await navigateViaSidebar(page, 'Sales');

    expect(customerCallCount).toBe(countBefore);
  });

  test('products list is not re-fetched on repeat navigation', async ({ page }) => {
    await loginViaAPI(page);

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

    // Navigate away (client-side)
    await navigateViaSidebar(page, 'Inventory');

    // Return (client-side) — no new product requests
    const countBefore = productCallCount;
    await navigateViaSidebar(page, 'Sales');

    expect(productCallCount).toBe(countBefore);
  });

  test('locations list is not re-fetched on repeat navigation to Sales', async ({ page }) => {
    await loginViaAPI(page);

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

    // Navigate away then back (client-side)
    await navigateViaSidebar(page, 'Inventory');
    const countBefore = locationCallCount;
    await navigateViaSidebar(page, 'Sales');

    expect(locationCallCount).toBe(countBefore);
  });

  test('customer cache is busted after creating a new customer', async ({ page }) => {
    await loginViaAPI(page);

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

    // Navigate to Customers page (client-side) and create a new one (mutates the data → busts cache)
    // Contacts defaults to the Suppliers tab -- switch to Customers first.
    await navigateViaSidebar(page, 'Contacts');
    await page.getByRole('tab', { name: 'Customers' }).click();
    await page.getByRole('button', { name: 'Add Customer' }).click();
    const name = `Cache Bust ${Date.now()}`;
    await page.getByPlaceholder('Customer name').fill(name);
    await page.getByRole('button', { name: 'Save Customer' }).click();
    await page.getByRole('dialog').waitFor({ state: 'hidden' });

    // After mutation the cache should be invalidated; re-visiting Sales (client-side) must fire a new request.
    // Wait for the specific bare-/customers response rather than generic
    // networkidle -- Angular's post-navigation subscribe() can fire the
    // fetch slightly later than the idle-detection window, which flaked
    // this assertion intermittently when run alongside the other tests.
    const countBeforeReturn = customerCallCount;
    const freshCustomerFetch = page.waitForResponse(
      (r) => r.url().includes('/customers') && !r.url().includes('/customers/') && r.request().method() === 'GET',
      { timeout: 8_000 },
    );
    await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Sales' }).click();
    await freshCustomerFetch;

    // A fresh request must have fired after the mutation busted the cache
    expect(customerCallCount).toBeGreaterThan(countBeforeReturn);
    expect(customerCallCount).toBeGreaterThan(afterFirstLoad);
  });
});
