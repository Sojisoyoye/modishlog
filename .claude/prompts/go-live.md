Act as a Lead Software Engineer, and Principal Solution Architect for Modishlog. We are launching the MVP live to production on our custom domain (modishlog.com) in 4 days. 

Your objective is to review the workspace, locate our configuration scripts (Vercel, package.json, source middleware, database clients), and execute this Production-Readiness Checklist sequentially.

---

## 📋 TASK MASTER EPIC: PRODUCTION GO-LIVE READINESS CHECKLIST

### PHASE 1: COMPREHENSIVE SECURITY HARDENING
We are handling financial data, transactions, and store balances. Security must be bulletproof at the network and application layer.
- **Data Leakage & Tainting Verification:** Scan all server components, api endpoints, and server actions. Ensure that sensitive raw database records, full encryption strings, or backend tokens are strictly blocked from leaking to the client browser.
- **Auth Endpoint Protection:** Implement aggressive rate-limiting tokens or middleware protection rules on all sensitive routes (such as `/api/auth`, `/login`, and payment hooks) to block brute-force vectors.
- **Secure Cookie & Session Lifecycle:** Verify that all authentication tokens and session state cookies use strict production flags: `HttpOnly`, `Secure`, and `SameSite=Strict`.

---

### PHASE 2: LATENCY OPTIMIZATION & COMPUTE REGION ALIGNMENT
Because this is a POS application used on retail floors, speed and network latency directly determine checkout success.
- **Database & Server Function Alignment:** Inspect our cloud compute runtime config (e.g., Vercel Functions region). You must match the Vercel Function hosting region exactly with the physical region of our live production database cluster (e.g., us-east-1 to us-east-1). Eliminating cross-region network hops is mandatory to drop API latency below 200ms.
- **Connection Pooling Activation:** Ensure our database client (Prisma, Mongoose, or native driver) uses a strict connection pooler (like Prisma Accelerate or Supabase pooling proxies) to prevent serverless compute spikes from exhausting database sockets during sudden checkout surges.
- **Font & Asset Pruning:** Verify that all images, icons, and typography files are optimized or self-hosted locally to avoid external blocking network waterfalls.

---

### PHASE 3: RELIABILITY, ERROR TRACKING & FALLBACK SYSTEMS
If something breaks on launch day, we must know about it instantly before our users reach out to customer support.
- **Global Error Boundaries:** Audit the workspace for an overarching app boundary (e.g., a root error.tsx or global middleware boundary handler). If missing, generate a highly informative, user-friendly fallback component that securely catches uncaught exceptions without freezing the active DOM.
- **Telemetry & Sentry Setup:** Confirm that our error monitoring hooks (like Sentry or LogRocket log drains) are actively listening in production mode, reporting descriptive stack traces, and blocking personal client records (PII) from log streams.

---

### PHASE 4: ENVIRONMENT VALIDATION & DEPLOYMENT LOCK
Ensure the code compiled for our custom domain is completely decoupled from experimental setups.
- **Strict Dependency Pinning:** Scan our lockfile (`package-lock.json`, `pnpm-lock.yaml`, or `yarn.lock`). Ensure all active dependencies are structurally pinned and cached to prevent third-party framework updates from breaking the automated build on deployment day.
- **Production Pre-Flight Build Check:** Run a simulation locally using production mode flags (`npm run build` or framework equivalent) to proactively uncover TypeScript anomalies, lint breakages, or hidden optimization warnings before pushing directly to the staging queue.

---

### PHASE 5: LIVE RUNTIME HEALTH CHECKS
- **Live Health-Check Endpoint:** Implement an isolated, highly performant endpoint (`/api/health`) that runs a quick parallel verification on upstream APIs, cache layers, and the primary data store, returning a structured `200 OK` JSON if healthy.

---

Please acknowledge receipt of this Go-Live Architectural Epic, outline your structural code findings across our workspace files, and begin your verification passes.

create a task master task for this and /batch for implementation