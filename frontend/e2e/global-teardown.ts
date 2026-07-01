/**
 * Playwright global teardown — runs once after the entire E2E suite.
 *
 * Nothing to do here: the test DB uses a tmpfs volume in docker-compose.e2e.yml
 * so its data is discarded when the container stops. This hook exists as a
 * placeholder for future cleanup (e.g. downloading failure screenshots).
 */

export default async function globalTeardown(): Promise<void> {
  console.log('[e2e teardown] Suite complete. Test DB data is ephemeral (tmpfs).');
}
