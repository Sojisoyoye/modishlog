import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts', // only files inside e2e/
  testIgnore: '**/business-isolation-verify.spec.ts', // requires live dev DB — run via isolation-verify.config.ts
  fullyParallel: false, // sequential — tests share the same backend DB
  // fullyParallel only serializes tests *within* a file — without pinning
  // workers, Playwright still runs multiple spec files concurrently across
  // workers, racing each other against the same shared test-DB/business
  // state and doubling CPU/browser load on the CI runner.
  workers: 1,
  retries: 0,
  timeout: 30_000,
  reporter: [['list']],

  // Runs before/after the entire suite — resets the isolated test DB so that
  // E2E runs NEVER touch the dev DB holding the migrated POS dataset.
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',

  use: {
    baseURL: 'http://localhost:4200',
    locale: 'en-US',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
