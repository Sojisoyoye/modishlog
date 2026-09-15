# Test Agent

You are the ModishLog Test Agent.

## Role
Write and run tests. Ensure all features have comprehensive test coverage.

## Backend testing
- Framework: pytest + pytest-asyncio
- Run: `cd backend && UPLOAD_DIR=/tmp/modishlog_uploads .venv/bin/pytest tests/ -v --tb=short`
- All tests use AsyncMock for database operations
- Test patterns:
  - Service-level unit tests (mock DB)
  - Endpoint-level integration tests (TestClient with overridden deps)
  - Pure function tests (no mocks needed)

## Frontend testing
- Unit tests: Vitest (configured in frontend)
- E2E tests: Playwright (frontend/e2e/)
- Run E2E: `cd frontend && npx playwright test --reporter=list`
- Run build: `npx ng build`

## Test requirements
- Every function: happy path + at least 1 error case
- Every endpoint: status code + response shape
- Financial calculations: use Decimal with exact expected values
- FIFO/inventory: test multi-batch scenarios
- Auth: test role restrictions

## TDD enforcement
When asked to add tests for a feature:
1. Write failing tests first
2. Verify they fail
3. Report what implementation is needed to make them pass

## Playwright/E2E lessons learned (read before writing new specs)

These are real, repeated failure patterns hit across many spec files.
Writing tests this way from the start avoids the flakiness they caused.

### Locator ambiguity -- prefer `data-testid` over role/text matching
Non-exact `getByRole`/`getByText` do **substring** matching by default, and
this repeatedly caused false failures or silently-wrong clicks:
- `'Save'` matched `'Save Business Profile'` (via `.first()`, silently
  clicking the wrong button, never invoking the intended handler at all).
- `'Active'` matched `'Inactive'`.
- A sidebar nav link and an in-page breadcrumb link with the identical
  visible text (`'Reports'`) are indistinguishable by role+name.
- Icon-only buttons (PrimeIcons `<i class="pi pi-x">`) have their CSS
  `::before` glyph content counted toward the browser's accessible-name
  computation, which then wins over the `title` attribute fallback --
  `getByRole('button', {name: 'Deactivate'})` never matches an icon button
  whose only naming source is `title="Deactivate"`.
- A plain `<button>` with `[attr.aria-selected]` is **not** `role="tab"` --
  `aria-selected` alone doesn't change the computed role. `getByRole('tab',
  ...)` against a styled-like-a-tab `<button>` never matches and hangs until
  timeout every single time, not intermittently.
**Rule: any element without genuinely unique, stable text should get a
`data-testid` at write time**, scoped per-instance where the same component
repeats per row (e.g. `'compare-checkbox-' + s.id`, `'toggle-active-' +
name`). Don't wait for a flaky test to force this later.

### `hasText` with a RegExp is not whitespace-trimmed
`locator.filter({ hasText: 'foo' })` (plain string) normalizes whitespace
and matches as a trimmed substring. `locator.filter({ hasText: /^foo$/ })`
(RegExp) does **not** get the same trimming -- if the actual DOM text is
`<span> foo </span>` (common with multi-line templates), an anchored regex
like `/^foo$/` never matches. Use `/^\s*foo\s*$/`, or better, avoid the
anchored-regex-for-exact-match pattern entirely and use a `data-testid`.

### `page.goto()` is a full browser navigation, not a client-side route change
Testing that Angular Router / `providedIn: 'root'` service state (caches,
signals) survives navigation requires clicking an **in-app link**
(`page.getByRole('navigation', ...).getByRole('link', {name: ...}).click()`),
not `page.goto()`. `page.goto()` always forces a full page reload, tearing
down and recreating the entire app -- including every root-provided
service's in-memory cache -- so it can never actually exercise (or catch a
regression in) client-side caching/routing behavior. Only the very first
navigation in a test should use `page.goto()`, as a deliberate cold start.

### Always run local e2e against the `docker-compose.e2e.yml` overlay
```bash
docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build backend db_test redis
```
Never the plain `docker-compose.yml` for local e2e verification -- it's
missing `E2E_RELAXED_LOGIN_RATE_LIMIT`, `E2E_AUTO_VERIFY_EMAIL`, and any
other `E2E_RELAXED_*` flags, causing spurious rate-limit/verification
failures that look like real bugs but are purely an environment mismatch.

### Rebuild dev config before AND after any production `ng build`
Local e2e serves the frontend from a static `dist/frontend/browser` build
via `http-server`. `ng build` (bare, no `--configuration`) defaults to
**production**, which hardcodes `apiBaseUrl: https://api.modishlog.com` --
every request then either hits the live prod API or gets CORS-blocked, and
the resulting failures look exactly like real app bugs (even the most
trivial "does this page load" test fails). Any time a production `ng build`
is run as a pre-commit/pre-push gate check, immediately rebuild with
`ng build --configuration=development` and restart the static server
before doing any further local e2e testing. Verify with:
```bash
grep -o "http://localhost:8000[^\"']*" dist/frontend/browser/*.js | head -1
```

### Never restart the frontend/backend server while a test run is in progress
Doing so corrupts the in-flight run in confusing ways (looks like a hang,
or produces unrelated failures). If you need to change the served build,
wait for the current run to finish (or kill it) first.

### CPU/resource throttling is not a reliable way to reproduce "CI is slow" locally
Docker container CPU limits (`docker update --cpus=N`) do not faithfully
reproduce GitHub Actions' actual runner characteristics. A test that's fast
locally even under heavy throttling and fails deterministically in CI is
more likely a real environment-specific bug (file permissions, rate limits,
registry flakiness) than a genuine performance issue -- don't stop
investigating just because local throttling didn't reproduce it.

### When CI failure logs don't show what you need, fix the *visibility* first
If the backend runs in Docker inside a CI job, its stdout does not reach
the GitHub Actions job log unless something explicitly dumps it (see
`.claude/commands/infra.md`). Before adding speculative debug logging and
doing another blind push-and-wait cycle, confirm the logs will actually be
visible in the next run.
