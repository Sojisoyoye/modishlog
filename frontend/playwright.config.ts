import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts', // only files inside e2e/
  fullyParallel: false, // sequential — tests share the same backend DB
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
