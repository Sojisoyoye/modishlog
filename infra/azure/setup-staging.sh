#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ModishLog — one-time Azure staging environment setup
# Run this ONCE to bootstrap the Azure resources.
# After that, CI/CD (deploy-staging.yml) handles all updates.
#
# Prerequisites:
#   - az CLI installed and logged in (az login)
#   - Docker images already pushed to GHCR (run the build-images workflow first)
#   - Required env vars exported (see .env.staging.example)
#
# Usage:
#   export STAGING_DATABASE_URL="postgresql+asyncpg://..."
#   export STAGING_SECRET_KEY="$(openssl rand -hex 32)"
#   export STAGING_CORS_ORIGINS="https://modishlog-staging.vercel.app"
#   export GHCR_TOKEN="ghp_..."
#   bash infra/azure/setup-staging.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SUBSCRIPTION_ID="8b21f152-e36b-4d53-9b88-70fc38d906bc"
RESOURCE_GROUP="rg-modishlog-staging"
LOCATION="germanywestcentral"
CAE_NAME="cae-modishlog"
APP_NAME="modishlog-backend-staging"
GHCR_REGISTRY="ghcr.io"
GHCR_USERNAME="sojisoyoye"
IMAGE="ghcr.io/sojisoyoye/modishlog/backend:staging"

# Required env vars
: "${STAGING_DATABASE_URL:?Set STAGING_DATABASE_URL}"
: "${STAGING_SECRET_KEY:?Set STAGING_SECRET_KEY}"
: "${STAGING_CORS_ORIGINS:?Set STAGING_CORS_ORIGINS}"
: "${GHCR_TOKEN:?Set GHCR_TOKEN}"

echo "▶ Setting subscription..."
az account set --subscription "$SUBSCRIPTION_ID"

echo "▶ Creating resource group: $RESOURCE_GROUP ..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output table

echo "▶ Creating Container Apps environment: $CAE_NAME ..."
az containerapp env create \
  --name "$CAE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output table

echo "▶ Creating backend Container App: $APP_NAME ..."
az containerapp create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CAE_NAME" \
  --image "$IMAGE" \
  --registry-server "$GHCR_REGISTRY" \
  --registry-username "$GHCR_USERNAME" \
  --registry-password "$GHCR_TOKEN" \
  --cpu 0.25 \
  --memory 0.5Gi \
  --min-replicas 0 \
  --max-replicas 1 \
  --ingress external \
  --target-port 8000 \
  --env-vars \
    "DATABASE_URL=secretref:database-url" \
    "SECRET_KEY=secretref:secret-key" \
    "CORS_ORIGINS=$STAGING_CORS_ORIGINS" \
    "ALGORITHM=HS256" \
    "ACCESS_TOKEN_EXPIRE_MINUTES=1440" \
    "ENVIRONMENT=staging" \
    "LOG_LEVEL=info" \
  --secrets \
    "database-url=$STAGING_DATABASE_URL" \
    "secret-key=$STAGING_SECRET_KEY" \
  --output table

echo ""
echo "▶ Running database migrations..."
az containerapp job create \
  --name "modishlog-migrate-staging" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CAE_NAME" \
  --trigger-type Manual \
  --replica-timeout 300 \
  --image "$IMAGE" \
  --registry-server "$GHCR_REGISTRY" \
  --registry-username "$GHCR_USERNAME" \
  --registry-password "$GHCR_TOKEN" \
  --cpu 0.25 \
  --memory 0.5Gi \
  --command "alembic" \
  --args "upgrade,head" \
  --env-vars \
    "DATABASE_URL=secretref:database-url" \
  --secrets \
    "database-url=$STAGING_DATABASE_URL" \
  --output table

az containerapp job start \
  --name "modishlog-migrate-staging" \
  --resource-group "$RESOURCE_GROUP"

echo ""
BACKEND_URL=$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

echo "✅ Staging backend deployed!"
echo ""
echo "   Backend URL : https://$BACKEND_URL"
echo "   Health check: https://$BACKEND_URL/health"
echo "   API docs    : https://$BACKEND_URL/docs"
echo ""
echo "Next steps:"
echo "  1. Set STAGING_API_URL=https://$BACKEND_URL in GitHub Actions secrets"
echo "  2. Set STAGING_CORS_ORIGINS to include your Vercel URL, then re-run:"
echo "       az containerapp update --name $APP_NAME --resource-group $RESOURCE_GROUP \\"
echo "         --set-env-vars CORS_ORIGINS=https://your-vercel-url.vercel.app"
echo "  3. Push to main to trigger the full CI/CD pipeline"
