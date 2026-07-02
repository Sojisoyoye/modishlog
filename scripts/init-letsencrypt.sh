#!/usr/bin/env bash
# First-time Let's Encrypt SSL certificate setup for modishlog.com
# Run ONCE on the VPS before starting Nginx with SSL.
# Usage: bash scripts/init-letsencrypt.sh
set -euo pipefail

DOMAIN="modishlog.com"
EMAIL="soji.soyoye@gmail.com"
DEPLOY_DIR="${DEPLOY_DIR:-/root/modishlog}"

cd "$DEPLOY_DIR"

echo "🔐 Obtaining SSL certificate for $DOMAIN..."

# Start Nginx with HTTP-only config to serve the ACME challenge
docker compose -f docker-compose.prod.yml up -d nginx

# Issue the certificate via webroot challenge
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  -d "$DOMAIN" \
  -d "www.$DOMAIN"

echo "✅ Certificate issued. Restarting Nginx with SSL..."
docker compose -f docker-compose.prod.yml restart nginx

echo "✅ modishlog.com is now serving HTTPS"
