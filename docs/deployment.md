# Deployment Guide

## Architecture overview

```
modishlog.com          → Vercel  (Angular SPA, production project)
api.modishlog.com      → Hetzner VPS 178.104.122.53 (FastAPI, Caddy SSL)
modishlog-staging.vercel.app → Vercel (staging project)
api-modishlog.modishstandard.com → Hetzner VPS (staging backend, port 8002)
```

Both environments run on the **same Hetzner server**. Caddy handles SSL termination and routing for all services on the server. The production backend sits at `/root/modishlog-prod/`; the staging backend at `/root/modishlog/`.

---

## Production — modishlog.com

### Components

| Component | Details |
|-----------|---------|
| Frontend | Vercel project `modishlog` — `npm run build` (`environment.prod.ts`, `apiBaseUrl: https://api.modishlog.com/api/v1`) |
| Backend | Docker container `modishlog-prod-backend`, port 8003, image `ghcr.io/sojisoyoye/modishlog/backend:production` |
| Database | PostgreSQL 15 container `modishlog_db`, Docker volume `modishlog-prod_modishlog_postgres_data` |
| SSL | Caddy auto-TLS (Let's Encrypt) |
| AI proxy | `cliproxy` container at `cliproxy.modishstandard.com` — same server |

### Deploy workflow

Triggered **manually** from GitHub Actions UI:

```
GitHub → Actions → "Deploy Production (modishlog.com)" → Run workflow
  image_tag: staging        ← reuse the latest tested staging image, or a specific SHA
  confirm:   deploy-production
```

Pipeline stages (in order):
1. **Confirm intent** — validates the `deploy-production` confirmation string
2. **Backend tests** — `pytest` against a temporary PostgreSQL 16 container
3. **CVE scan** — `pip-audit 2.10.1`; blocks deploy if any known CVE found
4. **Build & push production image** — tags `production` + `prod-<sha>` on GHCR; requires tests + scan
5. **Deploy frontend** *(parallel with backend deploy)* — `npx vercel@latest --prod` using `PRODUCTION_VERCEL_PROJECT_ID`
6. **Deploy backend** *(parallel with frontend deploy)* — SSH into Hetzner:
   - GHCR login
   - `docker compose pull backend`
   - `docker compose up -d db` + wait for `pg_isready`
   - `docker compose run --rm --no-deps backend alembic upgrade head`
   - Fix uploads volume permissions (alpine one-off)
   - `docker compose up -d --no-deps backend`
   - Smoke-test `https://api.modishlog.com/health` up to 2 min
7. **Notify** — reports success or failure

### GitHub secrets required

Set at: GitHub → Settings → Secrets and variables → Actions (repo-level) and Environments → production.

| Secret | Location | Value |
|--------|----------|-------|
| `PRODUCTION_HOST` | repo | `178.104.122.53` |
| `PRODUCTION_SSH_KEY` | production environment | contents of `~/.ssh/hetzner_modish` |
| `PRODUCTION_VERCEL_PROJECT_ID` | repo | `prj_vo4UE6aXYIG2Mrtc24ZZbykYzc2r` |
| `GHCR_TOKEN` | repo | GitHub PAT (`packages:read` + `packages:write`) |
| `VERCEL_TOKEN` | repo | Vercel API token |
| `VERCEL_ORG_ID` | repo | `team_y9YCMc4CohyNxSC2dqjBFzui` |

### Server layout

```
/root/modishlog-prod/
├── docker-compose.yml      # backend + postgres services
└── .env.production         # secrets (chmod 600, never committed)
```

`.env.production` contents:
```
POSTGRES_DB=modishlog
POSTGRES_USER=modishlog
POSTGRES_PASSWORD=<generated>
SECRET_KEY=<generated with: python3 -c "import secrets; print(secrets.token_hex(32))">
BACKEND_IMAGE=ghcr.io/sojisoyoye/modishlog/backend:production
ANTHROPIC_API_KEY=modish-cliproxy-key
ANTHROPIC_BASE_URL=https://cliproxy.modishstandard.com
```

### Caddy routing

The Caddyfile lives on the server at `/opt/modish/Caddyfile`. The production block:

```caddy
api.modishlog.com {
    @cors_preflight { method OPTIONS }
    handle @cors_preflight {
        header Access-Control-Allow-Origin "https://modishlog.com"
        header Access-Control-Allow-Credentials "true"
        header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        header Access-Control-Allow-Headers "Content-Type, Authorization, X-Requested-With"
        header Access-Control-Max-Age "3600"
        respond 204
    }
    handle {
        reverse_proxy 172.17.0.1:8003 {
            header_down -Access-Control-Allow-Origin
            header_down -Access-Control-Allow-Credentials
        }
        header Access-Control-Allow-Origin "https://modishlog.com"
        header Access-Control-Allow-Credentials "true"
    }
}
```

To update the Caddyfile and reload:
```bash
ssh root@178.104.122.53
nano /opt/modish/Caddyfile
docker exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

### Rollback

```bash
ssh root@178.104.122.53
cd /root/modishlog-prod
# Edit .env.production → change BACKEND_IMAGE to a previous tag (e.g. prod-abc1234)
docker compose --env-file .env.production up -d --no-deps --force-recreate backend
```

### Manual deploy (without CI)

```bash
# 1. Build and push image from local
docker build -t ghcr.io/sojisoyoye/modishlog/backend:production ./backend
echo $GHCR_TOKEN | docker login ghcr.io -u sojisoyoye --password-stdin
docker push ghcr.io/sojisoyoye/modishlog/backend:production

# 2. SSH in and deploy
ssh root@178.104.122.53 "
  cd /root/modishlog-prod
  echo \$GHCR_TOKEN | docker login ghcr.io -u sojisoyoye --password-stdin
  docker compose --env-file .env.production pull backend
  docker compose --env-file .env.production up -d db
  docker compose --env-file .env.production run --rm --no-deps backend alembic upgrade head
  docker run --rm -v modishlog-prod_modishlog_uploads:/app/uploads alpine sh -c 'mkdir -p /app/uploads/products /app/uploads/logos && chmod -R 777 /app/uploads'
  docker compose --env-file .env.production up -d --no-deps backend
"
```

---

## Staging — modishlog-staging.vercel.app

### Architecture notes

| Component | Service |
|-----------|---------|
| Frontend | Vercel (`modishlog-staging` project) — `npm run build:staging` |
| Backend API | Hetzner VPS, port 8002, image `ghcr.io/sojisoyoye/modishlog/backend:staging` |
| Database | Neon PostgreSQL staging branch (SSL required) |
| Config | `/root/modishlog/.env` on server |

### CI pipeline (triggered on every push to `main`)

1. **Backend tests** — `pytest` against a temporary PostgreSQL 16 container
2. **CVE scan** — `pip-audit 2.10.1`; blocks both frontend and backend deploys
3. **Build & push** (requires scan pass) — `staging-<sha>` + `staging` tags to GHCR
4. **Deploy frontend** (parallel with backend) — `npx vercel --prod`; `STAGING_API_URL` substituted via `sed` in `environment.staging.ts` at Vercel build time
5. **Deploy backend** (requires image push) — SSH into Hetzner: pull, `alembic upgrade head`, restart, health-check

### GitHub secrets required (staging)

| Secret | Purpose |
|--------|---------|
| `STAGING_DATABASE_URL` | Neon connection string (`postgresql+asyncpg://...@ep-xxx.neon.tech/neondb?sslmode=require`) |
| `STAGING_SECRET_KEY` | JWT signing key (`openssl rand -hex 32`) |
| `STAGING_CORS_ORIGINS` | Allowed frontend origins |
| `STAGING_API_URL` | Backend base URL — also set in Vercel dashboard env vars |
| `HETZNER_HOST` | Hetzner VPS IP (`178.104.122.53`) |
| `HETZNER_SSH_KEY` | Private SSH key for root access |
| `GHCR_TOKEN` | GitHub PAT (`packages:read` + `packages:write`) |
| `VERCEL_TOKEN` | Vercel API token |
| `VERCEL_ORG_ID` | Vercel org ID |
| `VERCEL_PROJECT_ID` | Staging project ID (`prj_m67UC2flGknEZWabTkwIoCLiJomw`) |

> **POS migration on staging:** SSH into the Hetzner server, `export POS_USERNAME=... POS_PASSWORD=...`, then run:
> `docker compose exec backend python scripts/pos_migrate.py --step=all`

### Troubleshooting

| Symptom | Check |
|---------|-------|
| CVE scan blocks deploy | Run `pip-audit -r backend/requirements.txt` locally; upgrade the flagged package |
| Backend health-check times out | `ssh root@178.104.122.53 "docker logs modishlog-backend --tail 50"` |
| Staging Vercel build fails | Confirm `STAGING_API_URL` is set in the `modishlog-staging` Vercel project → Environment Variables |
| Production Vercel build fails | Confirm `PRODUCTION_VERCEL_PROJECT_ID` GitHub secret matches `prj_vo4UE6aXYIG2Mrtc24ZZbykYzc2r` |
| GHCR pull denied on server | `echo $GHCR_TOKEN \| docker login ghcr.io -u sojisoyoye --password-stdin` |
| Alembic fails on migration | Check `DATABASE_URL` in `.env.production`; confirm the DB container is healthy |
| Production backend crash-loops | `docker logs modishlog-prod-backend --tail 50`; common cause: uploads volume permissions |
| `PermissionError: /app/uploads/products` | `docker run --rm -v modishlog-prod_modishlog_uploads:/app/uploads alpine chmod -R 777 /app/uploads` |

---

## Branch protection

`main` requires the `backend-tests / gate` status check to pass before any PR can merge. `gate` is a fan-in job that requires both `dependency-scan` and `test` to succeed. Configured via GitHub API — see `.github/workflows/backend-tests.yml`.
