# DNS Configuration — modishlog.com

DNS is managed on **Cloudflare** (zone ID `36eea4c43f0e35b17289e53618046aa4`).

## Current DNS records (live)

| Type | Name | Value | Proxy | TTL | Purpose |
|------|------|-------|-------|-----|---------|
| A | `api` | `178.104.122.53` | DNS-only | 300 | Backend API → Hetzner VPS; Caddy handles SSL |
| A | `api.staging` | `178.104.122.53` | DNS-only | 300 | Staging API → same Hetzner VPS; Caddy handles SSL |
| A | `staging` | `76.76.21.21` | DNS-only | 300 | Staging frontend → Vercel |
| CNAME | `@` | `cname.vercel-dns.com` | DNS-only | 300 | Apex domain → Vercel (Cloudflare CNAME flattening) |
| CNAME | `www` | `cname.vercel-dns.com` | DNS-only | 300 | www → Vercel |

> **Why DNS-only (not proxied)?** Caddy on Hetzner obtains its own Let's Encrypt certificate for `api.modishlog.com` using the HTTP challenge. Cloudflare proxying would intercept the ACME challenge and prevent cert issuance. Vercel similarly manages its own TLS for `modishlog.com`.

## Transactional email (Resend) — SPF/DKIM/DMARC (task 232)

`modishlog.com` is added and **verified** in Resend (domain id
`453a9b9e-12a4-4855-86e1-072a8cd37b3c`, region `eu-west-1`) — confirmed via
`GET /domains/{id}` returning `"status": "verified"` for all four records
below. Without these, mail sent via `RESEND_API_KEY` (task 212) would very
likely land in spam or be rejected outright by Gmail/Outlook/Apple Mail,
silently breaking the email-verification and forgot-password flows (PR #375)
for any real user.

| Type | Name | Value | Proxy | Purpose |
|------|------|-------|-------|---------|
| TXT | `resend._domainkey` | `p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDVuxW1M77C4zmbD1SYTsnUGdViidbxv1WHYAMzsFWc4qgL4CQxBqnOo3oLqzllsbhmKatnJWv4uDUP54hWPm3XBddvmD53FFIDEfXBJEih3CDW89iL2KVX8OIkdAVfcAu5lwxkR+deel6vGz20Xeq7tvYhNABSrC6eHC4BX4PPiQIDAQAB` | n/a | DKIM signing key |
| MX | `send` | `feedback-smtp.eu-west-1.amazonses.com` (priority 10) | n/a | Bounce/complaint feedback loop (part of Resend's SPF setup) |
| TXT | `send` | `v=spf1 include:amazonses.com ~all` | n/a | SPF — authorizes Amazon SES (Resend's sending infra) for the `send` subdomain |
| CNAME | `rsend` | `send.forge.rmta.net` | DNS-only | Resend's link/open tracking — **must not be proxied**, it isn't a web server |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:dmarc-reports@modishlog.com; fo=1` | n/a | DMARC policy — `p=none` (monitor-only) is the deliberate starting point; see below |

> **DMARC is intentionally `p=none` for now.** This only requests aggregate
> reports without affecting mail delivery — the safe way to confirm SPF/DKIM
> alignment is correct before tightening to `p=quarantine` or `p=reject`,
> which could otherwise silently drop legitimate mail if something's still
> misconfigured. Revisit after a couple of weeks of clean reports.
>
> **`rua=mailto:dmarc-reports@modishlog.com` needs a real mailbox to receive
> reports** — this was set as a placeholder and has not been confirmed to
> exist. If it doesn't, reports will simply fail to deliver (harmless, but
> you won't see them). Either create that mailbox/forward, or update the
> `_dmarc` TXT record to a real address.

Verify domain status anytime via:
```bash
RESEND_KEY="<your-resend-api-key-with-domain-access>"  # NOT the app's send-only key
curl -s "https://api.resend.com/domains/453a9b9e-12a4-4855-86e1-072a8cd37b3c" \
  -H "Authorization: Bearer $RESEND_KEY" | python3 -m json.tool
```

**Gmail delivery confirmed** (2026-09-12): a real test send via the Resend API
was received. **Still needed:** Outlook and Apple Mail specifically, and a
real verification/forgot-password email (not just a manual test send) — check
this for the first few sends from this freshly-verified domain, since it has
no sending reputation yet.

**FROM address is `contact@modishlog.com`, not `noreply@`** (changed
2026-09-12, `EMAILS_FROM_EMAIL` in `core/config.py` + all three env example
files + prod/staging compose defaults) — both current email types
(verification, forgot-password) are ones a user may legitimately need to
reply to for support. **`contact@modishlog.com` needs a real mailbox or
forward set up to actually receive those replies** — this could not be
verified via the Cloudflare API token in use (it lacks Email Routing
permission) and has not been otherwise confirmed to exist.

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
