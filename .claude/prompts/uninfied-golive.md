Act as a Principal DevOps Engineer, and Cloud Infrastructure Architect. We are launching Modishlog to production on our custom domain (modishlog.com). 

Your objective is to run a system-wide, exhaustive production-readiness pass across our codebase and infrastructure files to prepare us for launch. Execute the following seven-phase backlog systematically, self-testing your changes as you progress.

---

## 📋 MASTER EPIC: PRODUCTION GO-LIVE COMPLIANCE & ACCELERATION

### PHASE 1: COMPREHENSIVE SECURITY, WAITING & WAF ASSIGNMENT
Ensure our web perimeter is hardened against automated exploits and access vulnerabilities.
- **Content Security Policy (CSP):** Implement an explicit, rigid Content Security Policy header within our production middleware or configuration to stop cross-site scripting (XSS) and unauthorized script injection.
- **Web Application Firewall (WAF) & Rate Limiting:** Configure edge firewall parameters (such as Vercel WAF or custom rate-limiting middleware) to challenge malicious traffic, block unwanted scrapers, and safeguard sensitive auth paths like `/api/auth`.
- **Automated Dependency Scans:** Integrate or verify a dependency scanning script (e.g., automated vulnerability checks) in the build pipeline to catch and flag known third-party CVE vulnerabilities before compilation.

---

### PHASE 2: GLOBAL EDGE ACCELERATION & ASSET CACHING
Optimize asset delivery protocols to guarantee immediate interface rendering across retail spaces.
- **Font & Script Optimizations:** Audit layout templates. Ensure all font weights are self-hosted natively alongside static assets (eliminating layout shifts) and third-party script tags use deferral protocols to keep the main thread unblocked.
- **Static asset Caching Headers:** Inject strict immutable caching headers (`Cache-Control: public, max-age=31536000, immutable`) for all product images, icons, and interface shells stored in the public directory to lower origin request overhead.
- **Image Transcoding:** Ensure all product imagery utilizes modern optimized image formats (WebP/AVIF) with preset placeholder bounds to prevent layout shifts (CLS) on handheld screens.

---

### PHASE 3: COMPUTE REGION ALIGNMENT & CONNECTION POOLING
Eliminate latency spikes and socket starvation at the database tier.
- **Zero-Hop Regional Alignment:** Verify that our production serverless compute region matches the exact physical location of our production database cluster (e.g., us-east-1 to us-east-1). Cross-region compute-to-database requests must be strictly avoided.
- **Socket Connection Pooling Proxy:** Implement and force all production database drivers to connect through a persistent pooling client or proxy layer (e.g., Prisma Accelerate or a connection pool proxy) to prevent sudden serverless scaling from crushing database socket thresholds.
- **Read/Write Splitting Routing:** Route data-heavy reporting cards and analytics over to asynchronous read-replicas, preserving our primary cluster's full bandwidth for transaction writes.

---

### PHASE 4: SEO INTEGRITY, CANONICAL HOOKS & DOMAIN ROUTING
Configure the custom apex domain mapping cleanly without introducing duplicate text index problems.
- **Canonical Apex Redirects:** Configure Vercel/domain routing configurations so that all requests to subdomains or staging configurations automatically issue a permanent 301 redirect to the primary domain: `https://modishlog.com`.
- **Search Metadata & Robots Configuration:** Generate a clean production `robots.txt` and an automated dynamic `sitemap.xml` file. Inject clear meta tags to prevent search engines from index-crawling any auxiliary preview branches or staging URLs.

---

### PHASE 5: RECOVERY PLANS, ERROR WRAPPING & FAULT TOLERANCE
The application must fail gracefully without halting checkout terminals or corrupting point-of-sale data records.
- **Automated Backup & Restore Strategy:** Define and document a clear data backup schedule, confirming that automated multi-region snapshots occur daily and can be restored quickly without records degradation.
- **Network Retry Resiliency Middleware:** Wrap all internal API requests and third-party gateways in an automated retry wrapper using exponential backoff to handle minor connectivity drops gracefully.
- **Offline UI State Catching:** Provide a fallback UI banner for critical sales panels that instantly alerts handlers when connection is severed ("Network Disconnected - Local Data Cached Safely") instead of rendering an unhandled white-screen crash.

---

### PHASE 6: LOG TELEMETRY & STRATEGIC CONVENTIONS (`CLAUDE.md`)
- **Telemetry Configuration:** Verify that production crash logs are active, reporting clean stack traces, and utilizing strict sanitization filters to prevent personal client records (PII) from hitting external monitoring dashboards.
- **Generate RUNBOOK File:** Check a permanent `CLAUDE.md` file into the root of the project repository to enforce production architectural boundaries for any future Claude Code terminal sessions.

---

### PHASE 7: CLOSED TEST-DRIVEN COMPILATION LOOP
- Execute your code modifications through a strict, self-correcting validation lifecycle. Modify exactly one targeted file or system setting at a time. Immediately after every single modification, trigger the local build sequence and automated verification suites (`npm run build`, lint checkers, and unit test scripts). Do not proceed to the next task until the current step returns a stable green status.

---

Please acknowledge receipt of this Master Infrastructure & Code Go-Live Epic, generate the initial `PRODUCTION_SPEC.md` contract file, and output your initial structural findings to the terminal.

create a task master task for this and /batch for implementation.