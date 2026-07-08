Act as a, Principal DevOps Engineer, and Cloud Security Architect. Our MVP launch is imminent, and we need to establish a rock-solid, secure, and production-ready deployment pipeline to launch Modishlog on our custom domain: modishlog.com.

Your task is to scan the `modishlog` repository to understand the current configuration (e.g., checking Vercel configuration files like `vercel.json`, GitHub Actions workflows `.github/workflows/`, environment setups, or build scripts) to get full context on the current pipeline.

Once scanned, treat the following instructions as a strict Task Master backlog and implement or automate the following requirements sequentially:

---

## 📋 TASK MASTER EPIC: PRODUCTION LAUNCH READY (MODISHLOG.COM)

### PHASE 1: PIPELINE CONFIGURATION & MANUAL DEPLOYMENT GATES
Re-architect the current CI/CD deployment flow to introduce a rigorous, multi-stage pipeline with strict manual guardrails.
- **The Pipeline Flow:** Establish the following linear pipeline: Local Dev ➡️ Staging (Current Vercel configuration) ➡️ Production (`modishlog.com`).
- **Manual Prod Gate:** Ensure that pushes to the `main` or `release` branch automatically deploy to your Vercel staging environment. However, deploying from Staging to Production must NEVER be automatic. Configure a strict manual approval step (via GitHub Actions environments, Vercel production promotion rules, or manual release tag triggers) that requires a explicit human confirmation before pushing live.

---

### PHASE 2: SECURITY & PRODUCTION HARDENING
Review and enforce high-level web security configurations across the production environment.
- **SSL/TLS & Headers:** Configure the production router/framework to enforce strict HTTPS. Inject essential security headers, including Content Security Policy (CSP), HTTP Strict Transport Security (HSTS), X-Frame-Options (to prevent clickjacking), and X-Content-Type-Options.
- **Environment Variable Audit:** Scan the repo config to ensure no development or staging API keys, fallback mock configurations, or bypass tokens leach into the production runtime environment. Ensure all production variables are securely managed in Vercel/GitHub production environments.

---

### PHASE 3: METRICS, MONITORING & ERROR TRACKING
We cannot launch blindly. You must prepare the codebase for observability to catch bugs before users report them.
- **Error Tracking (Sentry/LogRocket/Equivalent):** Inspect the repository for existing tracking dependencies. If missing, configure a standard production error tracking system (like Sentry or a clean global error boundary middleware) that catches unhandled exceptions, reports them with stack traces, and alerts the team instantly without leaking PII (Personally Identifiable Information).
- **Structured Logging:** Ensure that production console output is clean, optimized, and does not print sensitive business data, user authorization headers, or database strings.

---

### PHASE 4: PRODUCTION READINESS & LIVE HEALTH CHECKS
Establish an automatic validation protocol to ensure the server and client bundles are fundamentally healthy before traffic hits them.
- **Health Check Endpoint:** Create or verify a lightweight, dedicated api route (e.g., `/api/health`) that runs a quick dependency check (verifying database connectivity and upstream API latency) and returns a clean `200 OK`.
- **Pre-Flight Smoke Test Script:** Build a minor automated pre-flight script or checklist configuration that checks asset compilation sizes, validates that the index page returns a successful HTML stream, and confirms the environment variables are successfully injected.

---

### PHASE 5: CUSTOM DOMAIN MAPPING (`modishlog.com`)
Provide the exact, production-ready routing strategy and infrastructure configuration needed to transition smoothly from the current staging domain to the custom production url.
- Generate a explicit technical summary outlining the precise DNS records (A Records, CNAME, or TXT for verification) that need to be attached to `modishlog.com` inside our DNS provider to map Vercel’s edge routing flawlessly with zero downtime.

---

Please acknowledge receipt of this production-readiness Task Epic, summarize the current pipeline configurations you discovered in the workspace files, and begin step-by-step implementation.

create a task master task for this and /batch for implementation