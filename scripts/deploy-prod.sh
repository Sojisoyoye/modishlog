#!/usr/bin/env bash
# Production deployment script — run on the Hetzner VPS
# Usage: bash scripts/deploy-prod.sh [image_tag]
set -euo pipefail

IMAGE_TAG="${1:-production}"
DEPLOY_DIR="${DEPLOY_DIR:-/root/modishlog}"

echo "🚀 Deploying modishlog backend (tag: $IMAGE_TAG) to production..."

cd "$DEPLOY_DIR"

# Pull latest image
echo "📦 Pulling $IMAGE_TAG..."
BACKEND_IMAGE="ghcr.io/sojisoyoye/modishlog/backend:$IMAGE_TAG" \
  docker compose -f docker-compose.prod.yml pull backend

# Run database migrations
echo "🗄️  Running Alembic migrations..."
docker compose -f docker-compose.prod.yml run --rm --no-deps backend alembic upgrade head

# Restart backend (zero-downtime: Nginx keeps serving while container restarts)
echo "🔄 Restarting backend..."
docker compose -f docker-compose.prod.yml up -d --no-deps backend

# Health check
echo "🏥 Waiting for health check..."
for i in $(seq 1 24); do
  STATUS=$(curl -sf -o /dev/null -w "%{http_code}" https://modishlog.com/health 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    echo "✅ Production healthy (modishlog.com)"
    exit 0
  fi
  echo "  attempt $i/24: HTTP $STATUS"
  sleep 5
done

echo "❌ Health check failed after 2 minutes — consider rollback:"
echo "   docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate backend"
exit 1
