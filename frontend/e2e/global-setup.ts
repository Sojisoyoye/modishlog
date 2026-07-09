/**
 * Playwright global setup — runs once before the entire E2E suite.
 *
 * Resets the isolated test DB (never touches the dev DB with migrated POS data)
 * by calling the backend reset script inside the running backend container.
 *
 * Requires the stack to be running with the e2e override:
 *   docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d
 */

import { execSync } from 'child_process';
import path from 'path';

// Always resolve docker-compose paths from the repo root, regardless of where
// `npx playwright test` is invoked (local: repo root, CI: frontend/ working-dir).
const REPO_ROOT = path.resolve(__dirname, '../..');

export default async function globalSetup(): Promise<void> {
  const RESET_TIMEOUT_MS = 60_000;

  console.log('[e2e setup] Resetting test DB...');
  try {
    execSync(
      'docker compose -f docker-compose.yml -f docker-compose.e2e.yml exec -T backend ' +
        'python scripts/reset_test_db.py',
      { cwd: REPO_ROOT, stdio: 'inherit', timeout: RESET_TIMEOUT_MS }
    );
  } catch (err) {
    throw new Error(
      `[e2e setup] Test DB reset failed.\n` +
        `Make sure the e2e stack is running:\n` +
        `  docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d\n\n` +
        String(err)
    );
  }

  console.log('[e2e setup] Test DB ready.');
}
