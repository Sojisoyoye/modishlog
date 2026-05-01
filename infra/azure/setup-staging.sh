#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ModishLog — one-time Azure staging environment setup
# Run this ONCE to bootstrap the Azure resources.
# After that, CI/CD (deploy-staging.yml) handles all updates.
#
# Prerequisites:
#   - az CLI installed and logged in (az login)
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
# Reuse heimpath's existing Container App Environment — Azure student/free tier
# allows only 1 CAE per region per subscription.
CAE_NAME="cae-heimpath"
CAE_RESOURCE_GROUP="rg-heimpath-shared"
APP_NAME="modishlog-backend-staging"
GHCR_REGISTRY="ghcr.io"
GHCR_USERNAME="sojisoyoye"

# Bootstrap with a public placeholder image — no registry auth needed.
# CI/CD will replace this with the real image on the first push to main.
PLACEHOLDER_IMAGE="mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"

# Real image reference (used only to register GHCR credentials on the app)
REAL_IMAGE="ghcr.io/sojisoyoye/modishlog/backend:staging"

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
  --subscription "$SUBSCRIPTION_ID" \
  --output table

echo "▶ Creating backend Container App: $APP_NAME (placeholder image) ..."
# Uses a public placeholder so Azure provisions successfully before the real
# image is built. The Container App itself is in rg-modishlog-staging for
# isolation; it shares cae-heimpath environment (only 1 CAE allowed per region).
az containerapp create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --subscription "$SUBSCRIPTION_ID" \
  --environment "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$CAE_RESOURCE_GROUP/providers/Microsoft.App/managedEnvironments/$CAE_NAME" \
  --image "$PLACEHOLDER_IMAGE" \
  --cpu 0.25 \
  --memory 0.5Gi \
  --min-replicas 0 \
  --max-replicas 1 \
  --ingress external \
  --target-port 80 \
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

echo "▶ Registering GHCR credentials on the Container App ..."
# Register the registry so CI can update to the real image without extra flags
az containerapp registry set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --subscription "$SUBSCRIPTION_ID" \
  --server "$GHCR_REGISTRY" \
  --username "$GHCR_USERNAME" \
  --password "$GHCR_TOKEN"

echo "▶ Updating target port to 8000 for real image ..."
az containerapp ingress update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --subscription "$SUBSCRIPTION_ID" \
  --target-port 8000

echo ""
echo "▶ Creating database migration job (placeholder image) ..."
# Migration job also uses placeholder; CI updates it alongside the app image.
az containerapp job create \
  --name "modishlog-migrate-staging" \
  --resource-group "$RESOURCE_GROUP" \
  --subscription "$SUBSCRIPTION_ID" \
  --environment "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$CAE_RESOURCE_GROUP/providers/Microsoft.App/managedEnvironments/$CAE_NAME" \
  --trigger-type Manual \
  --replica-timeout 300 \
  --image "$PLACEHOLDER_IMAGE" \
  --cpu 0.25 \
  --memory 0.5Gi \
  --env-vars \
    "DATABASE_URL=secretref:database-url" \
  --secrets \
    "database-url=$STAGING_DATABASE_URL" \
  --output table

echo ""
BACKEND_URL=$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --subscription "$SUBSCRIPTION_ID" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

echo "✅ Azure resources provisioned!"
echo ""
echo "   Container App URL : https://$BACKEND_URL"
echo "   (currently serving placeholder — real image deploys on first CI push)"
echo ""
echo "Next steps:"
echo "  1. Merge the PR and push to main to trigger CI/CD"
echo "     CI will build the real image, push to GHCR, update the Container App,"
echo "     and run alembic migrations automatically."
echo ""
echo "  2. Set STAGING_API_URL=https://$BACKEND_URL in:"
echo "     a) GitHub Actions secrets (repo Settings → Secrets)"
echo "     b) Vercel project env vars (dashboard → Project → Settings → Environment Variables)"
echo ""
echo "  3. After Vercel deploys, update CORS to allow the Vercel URL:"
echo "       az containerapp update --name $APP_NAME \\"
echo "         --resource-group $RESOURCE_GROUP \\"
echo "         --subscription $SUBSCRIPTION_ID \\"
echo "         --set-env-vars CORS_ORIGINS=https://your-vercel-url.vercel.app"
