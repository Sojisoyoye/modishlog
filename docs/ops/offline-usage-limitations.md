# ModishLog — Offline Usage: What's Actually Supported (task #248)

## Why this exists

ModishLog has zero offline capability today — no IndexedDB/local caching, no
service worker, no offline-first sync. Given the 2-day launch timeline and
everything else already in flight, the decision was to launch online-only
and document that deliberately, rather than build offline resilience now or
leave it as a silent, undocumented gap a merchant discovers the hard way
mid-sale.

**This is the intended v1 behavior, not a bug.** Revisit building real
offline-first sync post-launch if merchants report this as a real-world
pain point (a trader on a spotty mobile connection losing a sale write is
the most likely concrete complaint).

---

## What this actually means for a user

ModishLog requires an active internet connection for every action that
writes data — recording a sale, adding a product, adjusting stock, creating
a purchase order, etc. If the connection drops mid-action:

- The write does **not** happen. There is no local queue, no background
  retry, no "will sync when you're back online."
- The UI shows a clear error, not a silent hang or a false success message
  — every write flow's `error:` handler resets its loading state and shows
  an error toast (e.g. `sales-page.component.ts`'s `submitEntries()` →
  `messageService.add({severity: 'error', ...})`), which fires for a
  genuine dropped connection exactly the same way it fires for any other
  request failure (Angular's `HttpClient` still calls `error:` on a network
  failure — it isn't swallowed). Verified end-to-end for the sales-recording
  flow specifically (the flow most likely to be interrupted mid-sale, on a
  phone, in a shop) via `frontend/e2e/sales-network-failure.spec.ts`, which
  simulates a genuinely dropped connection (`route.abort('failed')`, not
  just an HTTP error status) and confirms the form shows
  "Failed to record sales" and re-enables, rather than hanging.
- Already-loaded pages/data stay visible (nothing crashes), but nothing new
  can be fetched or saved until the connection returns.
- A persistent banner (`OfflineService`, `frontend/src/app/layout/shell/shell.component.ts`)
  appears app-wide whenever the browser itself reports being offline
  (`navigator.onLine` / the `online`/`offline` window events) — "Network
  disconnected — last data cached locally. Reconnecting…". This catches the
  "wifi/data is fully down" case in real time. It does **not** catch every
  possible network failure — a slow/flaky connection where the browser
  still thinks it's online but a specific request times out or gets reset
  is only surfaced by that request's own error toast, not the banner.

## What is explicitly NOT supported

- Queuing a write made while offline to replay once reconnected.
- Any local-first data store (IndexedDB, service worker cache, etc.).
- Partial/optimistic UI updates that later reconcile with the server.

## If this needs to change post-launch

The two entry points to reconsider are `OfflineService`
(`frontend/src/app/core/services/offline.service.ts`, currently only
browser online/offline events) and each feature's own write-error handler
(currently: show a toast, discard the attempt). A real fix would mean
picking an actual offline-sync strategy (service worker + IndexedDB queue
is the standard approach) — a genuinely new architecture decision, not a
small patch, and shouldn't be started without first confirming it's worth
the complexity against real merchant feedback.
