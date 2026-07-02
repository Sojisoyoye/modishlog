# DNS Cutover Runbook — modishlog.com

## Prerequisites
- Production VPS provisioned and IP known
- Nginx SSL certificates issued via `scripts/init-letsencrypt.sh`
- Backend health check passing at `http://<VPS_IP>/health`

## DNS Records to Create

Add these at your DNS provider (e.g. Cloudflare, Namecheap, Route 53):

| Type  | Name  | Value            | TTL  | Notes                          |
|-------|-------|------------------|------|--------------------------------|
| A     | @     | `<VPS_IP>`       | 300  | Apex domain → VPS (lower TTL for cutover) |
| A     | www   | `<VPS_IP>`       | 300  | www → VPS (Nginx redirects to apex) |
| CAA   | @     | `0 issue "letsencrypt.org"` | 3600 | Restrict cert issuance to Let's Encrypt |
| TXT   | @     | (domain verification if required by provider) | — | — |

## Cutover Steps

1. **24 hours before cutover**: Lower TTL to 300s on existing DNS records so propagation is fast after cutover.

2. **Deploy to VPS**: Ensure `docker compose -f docker-compose.prod.yml up -d` is running and `curl http://<VPS_IP>/health` returns `{"status":"healthy"}`.

3. **Issue SSL cert** (first time only):
   ```bash
   bash scripts/init-letsencrypt.sh
   ```

4. **Update DNS**: At your registrar, point A record `@` and `www` to `<VPS_IP>`.

5. **Verify propagation**:
   ```bash
   dig A modishlog.com +short      # should return VPS_IP
   dig A www.modishlog.com +short  # should return VPS_IP
   ```

6. **Smoke test**:
   ```bash
   curl -I http://modishlog.com         # → 301 to https://
   curl -I http://www.modishlog.com     # → 301 to https://modishlog.com
   curl -I https://modishlog.com        # → 200, check HSTS header
   curl https://modishlog.com/health    # → {"status":"healthy"}
   ```

7. **After 48h stable**: Raise TTL to 3600s.

8. **HSTS Preload** (after 30 days stable): Submit to https://hstspreload.org

## Rollback

If the new VPS is broken, point DNS back to the previous server IP. Propagation takes up to TTL seconds (300s during cutover window).

## SSL Renewal

Certbot runs automatically every 12 hours inside the `certbot` Docker service. No manual action needed.

To renew manually:
```bash
docker compose -f docker-compose.prod.yml run --rm certbot renew
docker compose -f docker-compose.prod.yml restart nginx
```
