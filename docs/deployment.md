# Staging Deployment

## Architecture

| Component | Service |
|-----------|---------|
| Frontend | Vercel (auto-deploy on push to `main`) |
| Backend API | Hetzner root server — Docker Compose over SSH |
| Database | Neon PostgreSQL (staging branch, SSL) |
| Docker registry | GitHub Container Registry (GHCR) |
| CI/CD | GitHub Actions — `.github/workflows/deploy-staging.yml` |

> **Migration note**: The backend was originally on Azure Container Apps (PR #21, Jun 2026)
> and migrated to Hetzner SSH (PR #56, Jun 2026) due to Azure student-tier limitations.
> `infra/azure/setup-staging.sh` is retained but not used by CI.

---

## CI pipeline (triggered on every push to `main`)

1. **Backend tests** — run `pytest tests/ --tb=short -q` against a temporary PostgreSQL 16 container
2. **Build & push** (parallel with step 3, requires step 1) — build Docker image, tag `staging-<sha>` + `staging`, push to GHCR
3. **Deploy frontend** (parallel with step 2, requires step 1) — `npx vercel@latest --prod`
4. **Deploy backend** (requires step 2) — SSH into Hetzner server:
   - `echo $GHCR_TOKEN | docker login ghcr.io -u sojisoyoye --password-stdin`
   - `docker-compose pull backend`
   - `docker-compose run --rm --no-deps backend alembic upgrade head`
   - `docker-compose up -d --no-deps backend`
   - Health-check `GET /health` every 5 s for up to 2 min

---

## GitHub Actions secrets required

| Secret | Purpose |
|--------|---------|
| `STAGING_DATABASE_URL` | Neon connection string — `postgresql+asyncpg://...@ep-xxx.neon.tech/neondb?sslmode=require` |
| `STAGING_SECRET_KEY` | JWT signing key — generate with `openssl rand -hex 32` |
| `STAGING_CORS_ORIGINS` | Allowed frontend origins — e.g. `https://modishlog-staging.vercel.app` |
| `STAGING_API_URL` | Backend base URL — also set in Vercel dashboard env vars |
| `HETZNER_HOST` | IPv4 address of the Hetzner server |
| `HETZNER_SSH_KEY` | Private SSH key for root access to the Hetzner server |
| `GHCR_TOKEN` | GitHub PAT with `packages:read` + `packages:write` |
| `VERCEL_TOKEN` | Vercel API token |
| `VERCEL_ORG_ID` | Vercel org ID |
| `VERCEL_PROJECT_ID` | Vercel project ID |

Set these under: GitHub repo → Settings → Secrets and variables → Actions.

---

## Hetzner server setup (one-time)

```bash
# 1. Provision a Hetzner CX22 (or larger) — Ubuntu 22.04
# 2. SSH in as root and install Docker + Compose
apt-get update && apt-get install -y docker.io
curl -SL https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-x86_64 \
  -o /usr/local/bin/docker-compose && chmod +x /usr/local/bin/docker-compose

# 3. Create deploy directory and place docker-compose.staging.yml
mkdir -p /root/modishlog
scp docker-compose.staging.yml root@<server-ip>:/root/modishlog/docker-compose.yml

# 4. Create .env on the server with real values
cat > /root/modishlog/.env <<EOF
DATABASE_URL=<STAGING_DATABASE_URL>
SECRET_KEY=<STAGING_SECRET_KEY>
CORS_ORIGINS=<STAGING_CORS_ORIGINS>
ENVIRONMENT=staging
UPLOAD_DIR=/app/uploads
EOF

# 5. Pull and start once manually to verify
cd /root/modishlog
echo "<GHCR_TOKEN>" | docker login ghcr.io -u sojisoyoye --password-stdin
docker-compose pull
docker-compose up -d
```

---

## Frontend env injection

`STAGING_API_URL` is **not** a runtime env var — it is substituted at build time.
`vercel.json` `buildCommand` runs `sed` to replace `__STAGING_API_URL__` in
`frontend/src/environments/environment.staging.ts` before `ng build --configuration staging`.

Set `STAGING_API_URL` in **two** places:
1. GitHub Actions secret (used in CI logs / deploy commands)
2. Vercel project → Settings → Environment Variables (used by the `sed` substitution at Vercel build time)

---

## Manual deploy (without pushing to main)

```bash
# Build and push image
docker build -t ghcr.io/sojisoyoye/modishlog/backend:staging ./backend
echo $GHCR_TOKEN | docker login ghcr.io -u sojisoyoye --password-stdin
docker push ghcr.io/sojisoyoye/modishlog/backend:staging

# SSH in and restart
ssh root@<HETZNER_HOST> "
  cd /root/modishlog
  docker-compose pull backend
  docker-compose run --rm --no-deps backend alembic upgrade head
  docker-compose up -d --no-deps backend
"
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| CI fails at `pytest` before any deploy step | Check `SECRET_KEY` in workflow env — must be 32+ chars |
| Backend health-check times out | SSH in, run `docker-compose logs backend` |
| Vercel build fails | Check `STAGING_API_URL` is set in Vercel dashboard env vars |
| GHCR pull denied on server | Re-run `docker login ghcr.io` with a fresh PAT |
| Alembic fails on migration | Check `DATABASE_URL` in `/root/modishlog/.env`; confirm Neon staging branch is active |
