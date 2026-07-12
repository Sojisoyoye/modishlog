# Deployment

modishlog's backend runs on the shared Hetzner box (`178.104.122.53`) alongside trading-teddy,
heimpath, growthos, and modish-n8n. This box's shared reverse proxy (Caddy) and Claude API proxy
(cliproxy) are owned by [`modish-infra`](https://github.com/Sojisoyoye/modish-infra) — see that
repo's `HETZNER-INFRA.md` for the full shared-box reference (server access, every domain on the
box, DNS, general troubleshooting). This doc only covers what's specific to modishlog.

## Server directories

- **Staging**: `/root/modishlog/` on the shared box, container `modishlog-backend` (port 8002→8000)
- **Production**: `/root/modishlog-prod/` on the same box (despite the separate `PRODUCTION_HOST`
  secret — verified to resolve to the same IP), container `modishlog-prod-backend` (port 8003→8000)

Both containers are on the shared `modish_modish` Docker network (in addition to their own
`modishlog`/`modishlog_prod` networks), so Caddy reaches them by container name —
`modishlog-backend:8000` and `modishlog-prod-backend:8000` — not a host-bridge IP workaround.

## Caddy routing ownership (added 2026-07-12)

This repo used to manage the shared `/opt/modish/Caddyfile` directly via a manually-triggered
workflow (`configure-caddy.yml`) that parsed the file with Python and rewrote domain blocks in
place — a fragile pattern (the exact class of bug that silently broke trading-teddy/heimpath/
growthos's routing on 2026-07-10, when a hand-edit to that same shared file left their blocks
empty). That workflow has been removed.

modishlog now owns its own snippet at [`deploy/caddy/modishlog.caddy`](./deploy/caddy/modishlog.caddy),
covering both `api.modishlog.com` and `api.staging.modishlog.com` (including the CORS preflight
handling staging needs). `deploy-production.yml` and `deploy-staging.yml` each `scp` this file to
`/opt/modish/sites/modishlog.caddy` and run `caddy validate` before `caddy reload` on every deploy
— a bad snippet fails the deploy instead of reloading broken shared routing.

**Never hand-edit `/opt/modish/sites/modishlog.caddy` directly on the server** — edit
`deploy/caddy/modishlog.caddy` here and deploy, so the server and git stay in sync.

## Removed as part of this change

- **`.github/workflows/configure-caddy.yml`** — see above.
- **`nginx`/`certbot` services in `docker-compose.prod.yml`** — dead config from an earlier,
  standalone-server architecture, before this box's shared Caddy existed. Both domains were
  confirmed (via response headers showing `via: 1.1 Caddy`) to already route through the shared
  proxy, and `deploy-production.yml`'s script never actually started `nginx`/`certbot` anyway —
  they'd have conflicted with Caddy's port 80/443 binding if they ever had been brought up.
  `scripts/init-letsencrypt.sh` and the `nginx/` config directory are now unused too — left in
  place for now since they weren't fully audited, but worth a future cleanup pass.
