/**
 * Minimal Playwright config for the isolation-verify test.
 * No globalSetup so it runs against the live dev stack (not test DB).
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',  // config lives in e2e/, so '.' resolves to e2e/
  testMatch: 'business-isolation-verify.spec.ts',
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:4200',
    locale: 'en-US',
    // Slow down actions by 400ms so the user can follow along
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], slowMo: 400 },
    },
  ],
});
