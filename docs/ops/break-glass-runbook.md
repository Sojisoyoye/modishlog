# ModishLog — Break-Glass Access Runbook

## Why this exists

As of 2026-09-15, one person holds sole access to every system that matters
for keeping ModishLog running: the GitHub repo, the domain registrar,
production SSH, and every secret in between. If that person is unreachable
during the highest-risk window — a bad deploy right after launch, a
compromised secret needing rotation, a DNS emergency, an urgent PR that has
to merge — **nobody else can act**. This doc exists to fix that.

This is infrastructure access continuity — distinct from a customer-facing
support/escalation playbook (a separate concern).

**This is a template, not a finished runbook.** The technical specifics
below (secret names, workflow names, commands) are accurate as of this
writing. The `[ FILL IN ]` sections are the actual human decisions — who
the second person is, how they're reached, where the shared vault lives —
and only the founder can make those calls. Filling them in and actually
granting the access below is the real deliverable; this document alone
does not create break-glass access.

---

## Part 1 — Who

| | |
|---|---|
| Primary (founder) | Soji Soyoye — soji.soyoye@gmail.com |
| Second trusted person | [ FILL IN — name, relationship, how to reach them (phone, not just email) ] |
| Backup contact method if primary is unreachable | [ FILL IN — e.g. a phone number the second person can call/text ] |

---

## Part 2 — What to grant, and how

### 2a. GitHub

**Important finding**: there is currently no GitHub *organization* —
`github.com/Sojisoyoye/modishlog` is a personal-account repository. "Add a
second org owner" (the phrasing this task started from) isn't literally
possible today. Two real options, in order of effort:

- **Now (minimum viable)**: add the second person as a repo
  [Collaborator with the **Admin** role](https://github.com/Sojisoyoye/modishlog/settings/access)
  (Settings → Collaborators and teams → Add people). Admin-level repo
  access lets them merge PRs, manage repo secrets, and trigger
  `workflow_dispatch` actions (deploys, admin password reset, migrations)
  — covers every GitHub-side emergency scenario in Part 3 below.
- **Later (more robust)**: convert the repo into a GitHub Organization
  (Settings → General → "Transfer ownership" flow includes an option to
  move into a new org) and add the second person as an **Owner**. This is
  the only way to cover account-level actions (e.g. what happens if the
  founder's own GitHub account/2FA is lost) — a repo Collaborator, however
  privileged, still can't act if the founder's account itself is
  inaccessible and no one else has org-level control. Worth doing before
  this becomes a real problem, not urgent for launch week.

**Action**: [ ] Second person added as repo Admin collaborator (minimum for launch)
**Action**: [ ] Second person can log in and confirm access (don't just grant and assume)

### 2b. Domain registrar

`modishlog.com`'s DNS is managed via Cloudflare (zone id
`36eea4c43f0e35b17289e53618046aa4`, per prior session notes) — but the
**registrar of record** (who you'd contact to transfer, renew, or recover
the domain if locked out) needs to be confirmed; it may or may not be
Cloudflare itself.

**Action**: [ ] Confirm the actual registrar: `whois modishlog.com` or check the account where the domain was originally purchased
**Action**: [ ] [ FILL IN — registrar name ] account: add second person with real access (not just "notify them of the password" — an actual secondary login/recovery method the registrar supports)
**Action**: [ ] If DNS is indeed on Cloudflare separately from the registrar: add the second person to the Cloudflare account/zone too (Cloudflare supports multi-user account access under Members)

### 2c. Production SSH + secrets vault

Everything below currently lives only in the founder's local `.env` files
and GitHub Actions secrets (which the founder can see/edit, but a repo
Collaborator without a matching local checkout can't retrieve directly).

| Secret | Where it's used | Purpose |
|---|---|---|
| `PRODUCTION_SSH_KEY` / `PRODUCTION_HOST` | `deploy-production.yml`, `backup-production.yml` | SSH access to the Hetzner production VPS |
| `HETZNER_SSH_KEY` / `HETZNER_HOST` | `diagnose-prod.yml`, `admin-password-reset.yml` | Same VPS, used by diagnostic/admin workflows |
| `GHCR_TOKEN` | `deploy-production.yml` | Pushes/pulls container images from GitHub Container Registry |
| `ADMIN_PASSWORD` | `reset-admin-password.yml` | ModishLog's own in-app admin account password |
| Production `.env.production` (DB password, `SECRET_KEY`, `RESEND_API_KEY`, etc.) | Lives on the Hetzner box at `/root/modishlog-prod/.env.production` | The actual running app's runtime secrets |
| The raw SSH private key matching `PRODUCTION_SSH_KEY`/`HETZNER_SSH_KEY` | Founder's local machine | Needed for direct `ssh root@<host>` access outside of GitHub Actions |

**Action**: [ ] Set up a shared password manager vault (1Password or
Bitwarden — either has a "shared vault with restricted member access"
feature) with the second person added as a restricted member (access to
this vault only, not the founder's entire password manager)
**Action**: [ ] Copy the SSH private key + every secret in the table above
into that vault
**Action**: [ ] Verify the second person can actually open the vault and
read an entry — don't just assume the invite worked

---

## Part 3 — In an emergency, do X

Concrete answers for the four scenarios named in this task, assuming the
second person now has the access from Part 2.

### A bad deploy needs to be rolled back

1. Production deploys are image-tag based (`deploy-production.yml`,
   triggered by a release tag or manual `workflow_dispatch`) — there is no
   automatic rollback, so redeploy the previous known-good image tag:
   ```
   gh workflow run deploy-production.yml \
     -f image_tag=<previous-good-tag> \
     -f confirm=deploy-production
   ```
   (check `gh run list --workflow=deploy-production.yml` for recent tags
   that succeeded)
2. If the app is fully down and a redeploy isn't fast enough, SSH directly:
   `ssh root@178.104.122.53`, `cd /root/modishlog-prod`, and
   `docker compose down && docker compose up -d` to at least restart the
   current (even if broken) state while investigating.

### A secret needs to be rotated (e.g. a leaked API key)

1. Generate the new credential at the source (e.g. Resend dashboard,
   Anthropic console).
2. Update it in two places — GitHub Actions repo secrets (Settings →
   Secrets and variables → Actions) **and** `/root/modishlog-prod/
   .env.production` on the server directly via SSH, since the compose
   file reads from that file at container start, not from GitHub secrets
   at runtime.
3. Restart the affected container: `docker compose restart backend`
   (no full redeploy needed for an env-var-only change).

### A DNS/domain issue needs fixing

1. If it's a DNS record problem and Cloudflare manages the zone: log in to
   Cloudflare, zone `modishlog.com`, edit records directly (see Part 2b).
2. If it's a registrar-level problem (renewal, transfer lock, account
   recovery): use the registrar access from Part 2b — this is exactly the
   scenario that access exists for.

### An emergency PR needs to merge and the founder is unreachable

1. The second person (now a repo Admin per Part 2a) can review and merge
   directly. `main`'s branch protection only requires the `gate` check
   (see CI notes elsewhere in this repo) — if that's green, `gh pr merge
   --squash` is sufficient; `--admin` is available if a check is stuck
   pending on a docs/infra-only PR that doesn't trigger it.
2. If the change also needs deploying immediately, follow the deploy step
   under "a bad deploy" above (same `deploy-production.yml` workflow,
   just deploying forward instead of rolling back).

---

## Part 4 — Keeping this current

This document goes stale the moment a secret is rotated, a workflow is
renamed, or the second person changes. Re-read it end to end whenever any
of those happen, not just at launch.
