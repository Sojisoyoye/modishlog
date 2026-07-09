# ModishLog — Database Backup & Restore Runbook

## Targets

| Target | Value |
|--------|-------|
| **RTO** (Recovery Time Objective) | < 4 hours (manual restore from most-recent daily backup) |
| **RPO** (Recovery Point Objective) | < 24 hours (daily `pg_dump` cadence) |

## Backup Overview

ModishLog production runs on a single Hetzner VPS with a local PostgreSQL
container managed by Docker Compose.  Backups are compressed SQL dumps
(`pg_dump | gzip`) stored on the VPS and optionally synced to an off-site
location.

---

## Daily Backup Procedure

Run the following command daily (e.g. via cron at 02:00 local server time):

```bash
docker compose exec db pg_dump -U postgres modishlog \
  | gzip > ~/backups/modishlog-$(date +%Y%m%d).sql.gz
```

### Cron example (`crontab -e` on the VPS)

```cron
# ModishLog: daily DB backup at 02:00
0 2 * * * cd /opt/modishlog && docker compose exec -T db pg_dump -U postgres modishlog | gzip > ~/backups/modishlog-$(date +\%Y\%m\%d).sql.gz 2>> ~/backups/backup-errors.log
```

> **Note**: Use `-T` flag with `docker compose exec` in non-interactive (cron) context.

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
cd /opt/modishlog
docker compose stop backend
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
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS modishlog;"
docker compose exec db psql -U postgres -c "CREATE DATABASE modishlog;"
```

### Step 4: Restore from backup

```bash
BACKUP_FILE=~/backups/modishlog-20260708.sql.gz

gunzip -c "$BACKUP_FILE" | docker compose exec -T db psql -U postgres modishlog
```

### Step 5: Run pending Alembic migrations

If the backup is from a previous application version, apply schema migrations:

```bash
docker compose exec backend alembic upgrade head
```

### Step 6: Restart the application

```bash
docker compose start backend
```

### Step 7: Verify

```bash
# Check the health endpoint
curl https://app.modishlog.com/health

# Spot-check key counts
docker compose exec db psql -U postgres modishlog -c \
  "SELECT COUNT(*) FROM sales; SELECT COUNT(*) FROM products; SELECT COUNT(*) FROM users;"
```

---

## Monthly Restore Drill Checklist

Perform a test restore on a **separate staging environment** once per month
to verify backup integrity and practise the procedure:

- [ ] Identify the most-recent production backup file
- [ ] Copy backup file to staging VPS or local machine
- [ ] Stand up a fresh Docker Postgres container
- [ ] Run the restore procedure (Steps 3–6 above against staging)
- [ ] Verify row counts match production (within last 24h delta)
- [ ] Verify the health endpoint returns 200
- [ ] Verify a sample login works
- [ ] Record the drill date and outcome in this document:

| Date | Performed by | Backup date | Outcome | Notes |
|------|-------------|-------------|---------|-------|
| 2026-07-08 | — | — | — | Runbook created; drill pending |

---

## What to Do When the VPS is Unresponsive

1. **Check Hetzner Robot panel** — verify the VPS is powered on and network is healthy.
2. **Attempt SSH** — `ssh appuser@<VPS_IP>`. If connection refused, try the Hetzner console.
3. **Try hard reset** — Hetzner Robot → Server → Reset (if SSH is completely unavailable).
4. **Check disk space** — `df -h` — a full `/var` or `/opt` will freeze PostgreSQL.
5. **Check Docker daemon** — `systemctl status docker` and `docker compose ps`.
6. **Check container logs** — `docker compose logs --tail=100 backend db`.
7. **If data corruption is suspected** — stop backend, take a pg_dump, then investigate.
8. **If VPS is unrecoverable** — provision a fresh Hetzner VPS, restore from backup,
   update DNS A record to new IP.

**Estimated time for full rebuild**: 2–3 hours (provision + restore + DNS TTL propagation).

---

## Key Contacts & Credentials

> Store sensitive credentials in a password manager, not this file.

| Resource | Location |
|----------|----------|
| Hetzner Robot credentials | 1Password → "Modishlog Hetzner" |
| VPS SSH key | `~/.ssh/modishlog_hetzner_ed25519` |
| Database password | `POSTGRES_PASSWORD` in `/opt/modishlog/.env` |
| Backup storage credentials | 1Password → "Modishlog Backblaze" |

---

## Rate Limiting — Redis Configuration

### Current state (MVP / single instance)

Rate limiting falls back to **in-memory storage** when no Redis instance is
configured. This is acceptable for a single-instance MVP deployment:

- `/health/deep` will report `redis: not_configured` — this is expected and not an error.
- Rate-limit counters reset on backend container restart.
- Works correctly as long as only one backend worker is running.

### How to enable Redis (before scaling)

Enable Redis before adding a second backend worker or horizontal scaling.

**Step 1 — Add Redis service to `docker-compose.production.yml`:**

```yaml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

**Step 2 — Set the environment variable in `.env.production`:**

```bash
REDIS_URL=redis://redis:6379
```

**Step 3 — Restart the stack:**

```bash
docker compose -f docker-compose.production.yml up -d
```

**Step 4 — Verify:**

```bash
curl https://api.modishlog.com/health/deep | jq .redis
# Expected: "ok"
```

### When to do this

- Before deploying more than one backend container/worker
- Before adding a CDN or load balancer in front of the API
- If rate-limit counters surviving restarts becomes a compliance requirement

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

*Last updated: 2026-07-09 — Redis fallback docs + UptimeRobot monitoring setup*
