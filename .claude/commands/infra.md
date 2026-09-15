# Infra Agent

You are the ModishLog Infra Agent. Reference this before touching
Dockerfiles, docker-compose files, or GitHub Actions workflows -- these are
real bugs hit in production/CI this project has already paid for once.

## Role
Docker, docker-compose, and GitHub Actions changes for local dev, e2e CI,
staging, and production.

## Non-root Dockerfile USER + bind mount = broken permissions on Linux

**The bug:** `docker-compose.yml` bind-mounts `./backend:/app` for local dev
hot-reload. A bind mount **replaces the entire directory** at container
start, including whatever the image's Dockerfile did to it at build time --
so `RUN chown -R appuser /app` followed by `USER appuser` in the Dockerfile
has no effect once the bind mount is live. The container then runs as a
non-root user that doesn't actually own `/app` on the host filesystem.

**Why it's easy to miss:** macOS Docker Desktop / Colima's bind-mount
implementation is lenient about UID/GID matching, so this works "by
accident" in local dev. A native Linux host — **every GitHub Actions
runner** — enforces real UID ownership, so any runtime file write under the
bind-mounted path (e.g. `os.makedirs()` + `open(..., 'wb')` for an upload)
raises `PermissionError(13)` **100% of the time**, not intermittently.

**The fix, applied once already (don't reintroduce the bug for a new
directory):**
1. Any directory the app writes to at runtime under a bind-mounted path
   must instead be a **separate named Docker volume**, mounted at a path
   *outside* the bind mount (e.g. `uploads_data:/uploads`, not
   `uploads_data:/app/uploads`).
2. The app's config for that path (`UPLOAD_DIR` etc.) must point at the
   volume's mount path, not the default baked into `config.py`.
3. **Pre-create and chown that exact mount path in the Dockerfile, before
   `USER appuser`:**
   ```dockerfile
   RUN adduser --disabled-password --gecos "" appuser \
       && mkdir -p /uploads \
       && chown -R appuser /app /uploads
   USER appuser
   ```
   This matters because Docker copies a **freshly-created** named volume's
   initial ownership/content from whatever already exists at that path in
   the image. Skip this step and the volume defaults to root ownership,
   producing the identical `PermissionError` from a different cause.

**Before adding any new runtime-writable path:** ask whether it lives under
a bind-mounted directory in `docker-compose.yml`. If yes, it needs its own
named volume + Dockerfile pre-creation, not just `os.makedirs(exist_ok=True)`
in application code.

Production (`docker-compose.prod.yml`) does not bind-mount `/app` at all —
it runs the built image directly — so this class of bug doesn't apply
there, only to the local-dev/e2e compose stack.

## Docker-in-CI backend logs are invisible unless you dump them

If a service (e.g. `backend`) runs via `docker compose up -d` inside a
GitHub Actions job, **its stdout does not reach the job's log** just
because the container is running — Docker Compose's own log output only
surfaces in Actions when something explicitly runs
`docker compose logs <service>` in a step. This means: any `structlog`
info-level output the app emits *during* the test run (per-request timing,
warnings, anything) is completely invisible in CI no matter how much
diagnostic logging is added to the app, unless the workflow itself dumps
container logs.

**Standing rule:** every workflow that runs a Dockerized service under test
must have an unconditional log-dump step after the test step:
```yaml
- name: Show backend logs
  if: always()
  run: docker compose -f docker-compose.yml -f docker-compose.e2e.yml logs backend
```
Add this **before** adding speculative debug logging to chase a CI-only
failure — otherwise you're guessing blind across multiple push-and-wait
cycles for no reason.

## Retry transient Docker Hub pulls in CI

`docker compose up --build` pulling a public base image (e.g.
`postgres:16-alpine`) occasionally fails with a transient network error
("connection reset by peer", auth token fetch failures) on GitHub-hosted
runners — unrelated to app code, but it fails the entire job before any
test runs. Wrap compose-up steps that pull images in a retry loop:
```yaml
run: |
  for attempt in 1 2 3; do
    if docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build backend db_test redis; then
      exit 0
    fi
    echo "docker compose up failed (attempt $attempt/3), retrying in 10s..."
    sleep 10
  done
  exit 1
```

## Playwright browser binary caching across sharded CI jobs

If e2e tests run as N parallel matrix shards, each shard independently runs
`npx playwright install --with-deps chromium` from a cold cache by default
— N redundant downloads of the same browser binary per CI run. Playwright's
own install command already skips re-downloading a binary present at the
target revision, so caching `~/.cache/ms-playwright` (keyed on the
lockfile, so a Playwright version bump invalidates it) turns N downloads
into N cache restores:
```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/ms-playwright
    key: playwright-${{ runner.os }}-${{ hashFiles('frontend/package-lock.json') }}
```
Note: the `--with-deps` apt-level OS packages still install every time
regardless of cache hit, since each matrix job is a fresh, non-persisted
VM — only the browser download itself is saved. Savings are real but modest
(tens of seconds per shard); a bigger remaining lever if more speed is
needed is building the backend Docker image once (in a shared `build` job)
and having shards `pull` instead of each independently `--build`-ing it.
