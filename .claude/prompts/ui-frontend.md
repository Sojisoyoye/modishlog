Act as a Principal Frontend Security Engineer, and Lead UI Performance Architect. Modishlog is launching its MVP to production on modishlog.com. Your assignment is to execute this definitive all-in-one frontend compliance pass across the codebase to ensure world-class performance, bulletproof client-side security, strict WCAG 2.2 accessibility, and smooth data streaming on mobile viewports like the iPhone SE.

Execute the following six-phase backlog sequentially, validating and building the application after every single file mutation to prevent regressions.

---

## 📋 MASTER TASK: ALL-IN-ONE FRONTEND PERFORMANCE, SECURITY & ACCESSIBILITY AUDIT

### PHASE 1: CLIENT-SIDE SECURITY, SECRET ISOLATION & INPUT SANITIZATION
AI-generated code frequently leaks administrative configurations and leaves shortcut vulnerabilities. We must harden the client perimeter.
- **Secret Prefix Audit:** Systematically scan the codebase for any environment variable carrying a public prefix (e.g., `NEXT_PUBLIC_`). Ensure that server-only configurations, database URLs, administrative API keys, and private webhook tokens NEVER carry this prefix. 
- **XSS & InnerHTML Hardening:** Eliminate unsafe rendering shortcuts (e.g., raw `.innerHTML` mutations or framework blocks like `dangerouslySetInnerHTML`). Force all user-generated text inputs, product listings, and custom merchant notes to be securely escaped or processed through an explicit sanitizer library.
- **Verbose Error Masking:** Audit all user-facing notification hooks, toast alerts, and catch-blocks. Ensure production errors display clean, non-technical English messages to the shop owner (e.g., "Payment update failed"). Stack traces, database strings, and server-side file paths must be strictly masked.
- **CORS Domain Restrictions:** Ensure that Cross-Origin Resource Sharing (CORS) headers explicitly restrict API access to our custom domain (https://modishlog.com) and eliminate all loose wildcard (`*`) rules on authenticated routes.

---

### PHASE 2: CORE WEB VITALS & SKELETON PERFORMANCE LATENCY
A slow POS checkout destroys real-world business operations. We must optimize our loading states for maximum efficiency.
- **Layout Shift Elimination (CLS):** Enforce explicit width and height dimensions or strict aspect-ratio rules on all dynamic UI blocks, merchant logos, and product imagery placeholders to guarantee zero layout shifts when data streams in.
- **Dynamic Lazy-Loading:** Code-split and lazy-load heavy interactive modules (e.g., analytical graphs, complex reporting panels, or deep setup modals) to keep the initial client bundle lightweight.
- **Suspense & Streaming UI:** Wrap all database-dependent grids and summaries (like 'Today's Shop Summary' and full inventory lists) in explicit `<Suspense>` boundaries. Provide clean, accessible skeleton loaders so the application layout renders instantly while data resolves.

---

### PHASE 3: CURSOR PAGINATION, STREAMING & DATA CACHING
Loading massive inventory logs simultaneously will cause client-side browser tab lag and memory crashes.
- **Virtual Lists / Windowed Pagination:** For large tables or high-volume product grids, implement cursor-based pagination or virtual list rendering. The DOM must only render items currently visible in the active viewport.
- **Frictionless Controls:** Ensure pagination components utilize clean, thumb-friendly tap buttons. Display explicit counters (e.g., "Showing 1-20 of 450 items") using clear English text labels.
- **Stale-While-Revalidate Caching:** Integrate client-side fetch caching proxies (such as SWR or TanStack Query) to handle search arrays and prevent duplicate round-trip API requests when toggling filters.

---

### PHASE 4: EVENT LIFECYCLES & CLIENT MEMORY PRUNING
High-speed point-of-sale systems run continuously for hours on the sales floor. We must prevent UI degradation.
- **Event Listener Garbage Collection:** Audit components using scroll listeners, barcode scanning hardware hooks, or window observers. Ensure all global listeners are completely unbound and garbage-collected inside clean-up states (e.g., the return function of a React `useEffect`) when views unmount.
- **State Mutation Debouncing:** Implement strict micro-debouncing on keyword search inputs, item counter elements, and multi-location lookup fields to block repetitive client-side recalculations.

---

### PHASE 5: PRODUCTION ACCESSIBILITY (WCAG 2.2 COMPLIANCE)
Ensure the retail layout works seamlessly for operators navigating under intense, fast-paced store environments.
- **Tactile Touch Targets:** Ensure every interactive element, pagination selector, navigation link, and checkout button has a minimum tap target of 44x44px with adequate physical padding to eliminate mis-taps.
- **Label & Aria Alignment:** Ensure all input boxes and select elements are mapped to explicit `<label>` parameters or use descriptive `aria-label` fields. 
- **Aria-Live Live Updates:** Implement `aria-live="polite"` regions on the active shopping cart drawer and checkout counter alerts so that screen assistants automatically announce total changes without forcing a full page refresh.
- **Unique DOM IDs & Focus Traps:** Guarantee all DOM element `id` parameters are unique across the tree. Enforce strict keyboard focus traps inside all payment confirmation modals and alerts.

---

### PHASE 6: NETWORK RESILIENCY & CLOSED VALIDATION LOOP
- **Double-Submission Prevention:** Inject explicit loading states or disable submit buttons immediately upon user tap to prevent duplicate transaction charges during a slow network sync cycle.
- **Closed Pre-Flight Verification:** Execute these changes by modifying exactly one target file at a time. Immediately after every single update, trigger the local build sequence and validation suites (`npm run build`, lint checkers, and frontend test suites). Do not move to the next file until the current path compiles into production assets with a stable, zero-warning green status.

create a task master task for this and /batch for implementation