# ModishLog — Database Backup & Restore Runbook

## Targets

| Target | Value |
|--------|-------|
| **RTO** (Recovery Time Objective) | < 4 hours (manual restore from most-recent daily backup) |
| **RPO** (Recovery Point Objective) | < 24 hours (daily `pg_dump` cadence) |

## Backup Overview

ModishLog production runs on a single Hetzner VPS (`178.104.122.53`) with a
local PostgreSQL container managed by Docker Compose, deployed at
`/root/modishlog-prod/` (see `DEPLOYMENT.md`). Backups are compressed SQL
dumps (`pg_dump | gzip`) stored on the VPS at `~/backups/` and, as of task
233, automated daily via a scheduled GitHub Actions workflow
(`.github/workflows/backup-production.yml`) rather than a server-side cron
entry nobody would remember existed after a VPS rebuild.

---

## Daily Backup Procedure

**Automated** (as of task 233): `.github/workflows/backup-production.yml`
runs daily via `schedule: cron` and SSHes in to run the same command below,
using the existing `PRODUCTION_HOST`/`PRODUCTION_SSH_KEY` secrets already
used by `deploy-production.yml`.

Manual/on-demand version (matches what the workflow runs):

```bash
ssh root@178.104.122.53
cd /root/modishlog-prod
mkdir -p ~/backups
docker compose -f docker-compose.yml --env-file .env.production \
  exec -T db pg_dump -U modishlog modishlog \
  | gzip > ~/backups/modishlog-$(date +%Y%m%d-%H%M%S).sql.gz
```

> Postgres user is `modishlog` (from `POSTGRES_USER` in `.env.production`),
> **not** `postgres` — the default Postgres image doesn't create a
> `postgres` role when `POSTGRES_USER` is set to something else. The `db`
> service isn't exposed on any host port, so this must run via
> `docker compose exec`, not a direct `psql`/`pg_dump` from the host.

### Off-site sync (recommended)

```bash
# Sync backups to Backblaze B2 / S3-compatible storage
rclone sync ~/backups/ remote:modishlog-backups/ --min-age 1h
```

---

## Backup Retention Policy

| Age | Action |
|-----|--------|
| < 7 days | Keep all daily backups |
| 7–30 days | Keep weekly backups (delete intermediate days) |
| > 30 days | Delete (unless business compliance requires longer) |

```bash
# Prune backups older than 30 days
find ~/backups/ -name "modishlog-*.sql.gz" -mtime +30 -delete
```

---

## Restore Procedure

### Step 1: Stop the application

```bash
cd /root/modishlog-prod
docker compose -f docker-compose.yml --env-file .env.production stop backend
```

### Step 2: Identify the backup to restore

```bash
ls -lh ~/backups/modishlog-*.sql.gz
```

Choose the most-recent file before the data loss event.

### Step 3: Drop and recreate the database

> **WARNING**: This destroys all data in the `modishlog` database.
> Confirm you have a valid backup before proceeding.

```bash
docker compose -f docker-compose.yml --env-file .env.production exec db \
  psql -U modishlog -c "DROP DATABASE IF EXISTS modishlog;"
docker compose -f docker-compose.yml --env-file .env.production exec db \
  psql -U modishlog -c "CREATE DATABASE modishlog;"
```

### Step 4: Restore from backup

```bash
BACKUP_FILE=~/backups/modishlog-20260708-020000.sql.gz

gunzip -c "$BACKUP_FILE" | docker compose -f docker-compose.yml \
  --env-file .env.production exec -T db psql -U modishlog modishlog
```

### Step 5: Run pending Alembic migrations

If the backup is from a previous application version, apply schema migrations:

```bash
docker compose -f docker-compose.yml --env-file .env.production \
  run --rm --no-deps backend alembic upgrade head
```

### Step 6: Restart the application

```bash
docker compose -f docker-compose.yml --env-file .env.production start backend
```

### Step 7: Verify

```bash
# Check the health endpoint
curl https://api.modishlog.com/health

# Spot-check key counts
docker compose -f docker-compose.yml --env-file .env.production exec db \
  psql -U modishlog modishlog -c \
  "SELECT COUNT(*) FROM sales; SELECT COUNT(*) FROM products; SELECT COUNT(*) FROM users;"
```

---

## Monthly Restore Drill Checklist

Perform a test restore on a **separate scratch environment** (a local Docker
container, not staging — staging is a real environment with its own Neon DB,
not local Postgres, so "restore into staging" doesn't actually apply the way
this was originally worded) once per month to verify backup integrity and
practise the procedure:

- [x] Identify the most-recent production backup file
- [x] Copy backup file to a local machine
- [x] Stand up a fresh Docker Postgres container (matching prod's actual
      `postgres:15-alpine`, not whatever version happens to be handy)
- [x] Run the restore procedure (Steps 3–6 above, adapted for a local
      container instead of the prod compose stack)
- [x] Verify row counts match production
- [x] Verify the health endpoint returns 200 (ran the actual backend image
      against the restored DB, not just Postgres in isolation)
- [x] Verify a sample login works (confirmed real bcrypt hashes intact and
      the `/auth/login` code path executes correctly end-to-end against the
      restored data — didn't have an actual production password to log in
      with, so verified the mechanism instead of a literal successful login)
- [x] Record the drill date and outcome in this document:

| Date | Performed by | Backup date | Outcome | Notes |
|------|-------------|-------------|---------|-------|
| 2026-07-08 | — | — | — | Runbook created; drill pending |
| 2026-09-12 | Claude (ship session, SSH access confirmed by user) | 2026-09-12 18:25 UTC | **Pass** | Real `pg_dump` from production (21K compressed, 1 sale/1 product/2 users/2 businesses — small pre-launch dataset), restored into a local `postgres:15-alpine` container, `alembic upgrade head` applied cleanly (prod's `alembic_version` was `202e2d0f7c04`, several migrations behind repo `HEAD` `e580169665df` — see finding below), backend booted against restored DB and `/health` returned 200, row counts matched exactly, login endpoint correctly processed real user records (401 on wrong password, proving the full auth code path works). Also corrected this runbook's paths/usernames/filenames (`/opt/modishlog`→`/root/modishlog-prod`, `-U postgres`→`-U modishlog`, `docker-compose.production.yml`→`docker-compose.prod.yml`, `app.modishlog.com`→`api.modishlog.com`) — none of the original commands as written would have worked against the real server. |

> **Separate finding, not part of this drill**: production's `alembic_version`
> (`202e2d0f7c04`) is several migrations behind this repo's current `HEAD`
> (`e580169665df`) — `deploy-production.yml` is manual/tag-gated and hasn't
> been run recently, so production is running an older schema/image than
> what's on `main`. Not a backup/restore problem, but worth knowing before
> assuming production reflects recent work.

---

## What to Do When the VPS is Unresponsive

> **This box is shared** — `178.104.122.53` also hosts trading-teddy,
> heimpath, growthos, and modish-n8n (see `DEPLOYMENT.md`). A hard reset or
> rebuild affects all of them, not just modishlog. Coordinate before doing
> anything destructive here; this is not modishlog's dedicated VPS.

1. **Check Hetzner Robot panel** — verify the VPS is powered on and network is healthy.
2. **Attempt SSH** — `ssh -i ~/.ssh/hetzner_modish root@178.104.122.53`. If connection refused, try the Hetzner console.
3. **Try hard reset** — Hetzner Robot → Server → Reset (if SSH is completely unavailable) — see the shared-box warning above first.
4. **Check disk space** — `df -h` — a full disk will freeze PostgreSQL for every project on the box, not just modishlog.
5. **Check Docker daemon** — `systemctl status docker` and `docker compose ps` (run from `/root/modishlog-prod/`).
6. **Check container logs** — `docker compose -f docker-compose.yml --env-file .env.production logs --tail=100 backend db`.
7. **If data corruption is suspected** — stop backend, take a pg_dump, then investigate.
8. **If the shared box itself is unrecoverable** — this affects every project on it, not
   just modishlog; coordinate a full rebuild rather than treating it as a
   modishlog-only incident. `deploy-production.yml`/`deploy-staging.yml`'s
   scp steps mean the compose files themselves are recoverable from this
   repo — only server-local secrets (`.env.production`, the staging `.env`)
   and the Postgres data volume need restoring from backup.

---

## Key Contacts & Credentials

> Store sensitive credentials in a password manager, not this file.

| Resource | Location |
|----------|----------|
| Hetzner Robot credentials | 1Password (vault name unverified — confirm before relying on this) |
| VPS SSH key | `~/.ssh/hetzner_modish` |
| Database password | `POSTGRES_PASSWORD` in `/root/modishlog-prod/.env.production` |
| Backup storage credentials | 1Password (vault name unverified — confirm before relying on this; no off-site sync is actually configured yet, see below) |

---

## Rate Limiting — Redis Configuration

### Current state

`docker-compose.prod.yml` now defines a `redis` service and wires
`REDIS_URL` into the backend (task 212, fixed for real in task 254 after an
initial version broke the deploy pipeline — see git history on that file).
**This has not yet reached production** — `deploy-production.yml` is
manual/tag-gated and hasn't been run since. Confirmed live as of
2026-09-12: `curl https://api.modishlog.com/health/deep` still shows
`"redis": "not_configured"`. Staging already has this deployed and working
(`redis: ok`).

Until the next production deploy runs, rate limiting on production falls
back to in-memory storage — acceptable for the current single-worker MVP
deployment (gunicorn `--workers 2` in `docker-compose.prod.yml` means
counters aren't actually fully shared between the two workers today either,
worth knowing).

### After the next production deploy, verify:

```bash
curl https://api.modishlog.com/health/deep | jq .redis
# Expected: "ok"
```

---

## Monitoring

### UptimeRobot setup

Two HTTP monitors are configured in [UptimeRobot](https://uptimerobot.com):

| Monitor | URL | Interval |
|---------|-----|----------|
| API health | `https://api.modishlog.com/health` | 5 min |
| Frontend | `https://modishlog.com` | 5 min |

Alert contact: `soji.soyoye@gmail.com` — triggered after **2 consecutive failures**.

Dashboard screenshot: `docs/ops/uptime-monitoring-setup.png`

### Adding more alert contacts

Log in to UptimeRobot → **Alert Contacts** → **Add Alert Contact**.
Recommended: add an on-call email or phone number before handing off to another operator.

---

*Last updated: 2026-09-12 — task 233: first real backup/restore drill executed (pass), automated daily backup workflow added, corrected paths/usernames/filenames throughout that had never matched the real server*
