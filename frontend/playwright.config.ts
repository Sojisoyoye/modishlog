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
  // Retries only in CI -- a genuinely broken test should still fail fast
  // locally (0 retries), but CI runners see real variance in page-load /
  // render timing under shared load that a hand-tuned fixed timeout can't
  // fully absorb. A test that fails all 3 attempts in CI is still a hard
  // failure -- this doesn't mask real regressions, it just stops one slow
  // paint from failing an otherwise-correct test.
  retries: process.env.CI ? 2 : 0,
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
    // task #231: no automated coverage existed for Safari (WebKit) or a
    // real mobile device before this -- mobile-bottom-nav.spec.ts only
    // resizes the Chromium viewport, it doesn't exercise WebKit's actual
    // rendering engine, touch input, or Mobile Safari's user agent. Scoped
    // to @smoke-tagged tests only (grep) -- given the 2-day launch
    // timeline, running the full suite on every extra browser project
    // triples CI time/cost for coverage that's mostly redundant with
    // chromium; expand post-launch instead of gating launch on it.
    {
      name: 'webkit',
      grep: /@smoke/,
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'mobile',
      grep: /@smoke/,
      use: { ...devices['iPhone 13'] },
    },
  ],
});
