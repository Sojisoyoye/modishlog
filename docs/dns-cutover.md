# DNS Configuration — modishlog.com

DNS is managed on **Cloudflare** (zone ID `36eea4c43f0e35b17289e53618046aa4`).

## Current DNS records (live)

| Type | Name | Value | Proxy | TTL | Purpose |
|------|------|-------|-------|-----|---------|
| A | `api` | `178.104.122.53` | DNS-only | 300 | Backend API → Hetzner VPS; Caddy handles SSL |
| CNAME | `@` | `cname.vercel-dns.com` | DNS-only | 300 | Apex domain → Vercel (Cloudflare CNAME flattening) |
| CNAME | `www` | `cname.vercel-dns.com` | DNS-only | 300 | www → Vercel |

> **Why DNS-only (not proxied)?** Caddy on Hetzner obtains its own Let's Encrypt certificate for `api.modishlog.com` using the HTTP challenge. Cloudflare proxying would intercept the ACME challenge and prevent cert issuance. Vercel similarly manages its own TLS for `modishlog.com`.

## Vercel domain config

Both `modishlog.com` and `www.modishlog.com` are linked to the `modishlog` Vercel project (`prj_vo4UE6aXYIG2Mrtc24ZZbykYzc2r`). Vercel issues and renews the TLS certificate automatically.

## Updating DNS via Cloudflare API

```bash
CF_TOKEN="<your-cloudflare-api-token>"
ZONE_ID="36eea4c43f0e35b17289e53618046aa4"

# List current records
curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
  -H "Authorization: Bearer $CF_TOKEN" | python3 -m json.tool | grep -E '"name"|"content"|"id"'

# Update a record (replace <record-id> with the ID from the list above)
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/<record-id>" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "<new-value>"}'
```

The Cloudflare token is stored locally in `.env` as `CLOUDFLARE_TOKEN`.

## Re-pointing the backend to a different server

If the Hetzner VPS IP changes:

1. Update the `api` A record in Cloudflare to the new IP
2. Update the `PRODUCTION_HOST` GitHub secret
3. SSH into the new server and ensure `/root/modishlog-prod/` is set up with the compose file and `.env.production`
4. Caddy will auto-obtain a new TLS cert for `api.modishlog.com` on first request (requires port 80 open)

## Smoke tests

```bash
# Backend API
curl https://api.modishlog.com/health
# → {"status":"healthy","version":"1.0.0","db":"ok","timestamp":"..."}

# Frontend
curl -sI https://modishlog.com | head -5
# → HTTP/2 200

# www redirect (Vercel handles this)
curl -sI https://www.modishlog.com | head -3
# → HTTP/2 308 or 200 depending on Vercel config
```

## HSTS Preload

After 30 days of stable operation, submit `modishlog.com` to https://hstspreload.org to lock in HSTS across browsers. Requires `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` to be served — verify this is present on the Vercel response headers before submitting.
