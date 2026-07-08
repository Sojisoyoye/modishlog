# ModishLog — Pre-PR Risk Check

Run this before opening any PR. Feed it the current branch diff.
It checks only what is relevant to what changed — no false positives from unrelated code.

---

```xml
<task>
Review the diff of the current branch against main using `git diff main...HEAD`.
For each changed file, apply only the risk checks relevant to that file's domain.
Report PASS / FAIL / NOT APPLICABLE per category.
Only flag actual issues in the diff — do not audit unchanged code.
</task>

<how_to_run>
  Step 1: Run `git diff main...HEAD --stat` to see what changed.
  Step 2: Run `git diff main...HEAD` to read the full diff.
  Step 3: Work through each check below that applies to the changed files.
  Step 4: Report findings inline — PASS means verified clean, FAIL means
          do not open the PR until fixed, NOT APPLICABLE means the check
          does not apply to any file in this diff.
</how_to_run>

<checks>

  <!-- ─── Applies to: any backend/src/ service or router file ─────────────── -->
  <check id="S1" domain="Security" severity="Critical"
         applies_to="any backend/src/**/*.py">
    BUSINESS ISOLATION — every SELECT / UPDATE / DELETE on a business-scoped
    table must filter by business_id.

    Look for: new db.execute(select(Model)...) calls that lack
              .where(Model.business_id == current_user.business_id)
    Exceptions: tables without business_id (PasswordResetToken, RefreshToken,
                Business itself, FXRate which is global)

    FAIL if: any query on products / sales / orders / customers / suppliers /
             inventory / expenses / cashflow / pricing / ai_engine tables
             omits the business_id filter.
  </check>

  <check id="S2" domain="Security" severity="Critical"
         applies_to="any backend/src/**/*.py">
    NO RAW SQL — SQLAlchemy ORM only. text() is forbidden outside alembic/.

    Look for: text(, db.execute("SELECT, connection.execute("
    Exceptions: alembic/versions/*.py migration files only

    FAIL if: any raw SQL string found in src/ files.
  </check>

  <check id="S3" domain="Security" severity="High"
         applies_to="any backend/src/**/*.py">
    NO SECRETS IN LOGS — structlog calls must never include fields named
    password, secret, key, token, encrypted_value, api_key, or credential.

    Look for: logger.info(..., password=, log.debug(..., secret=,
              structlog.get_logger()...bind(key=
    FAIL if: any sensitive field name passed to any logger call.
  </check>

  <check id="S4" domain="Security" severity="High"
         applies_to="backend/src/auth/router.py, any new public endpoint">
    RATE LIMITING — all public endpoints (no auth required) must have
    @limiter.limit() decorator.

    Look for: new @router.post / @router.get routes that have no
              authentication dependency AND no @limiter.limit() decorator.
    Exceptions: /health endpoints

    FAIL if: any new unauthenticated endpoint lacks rate limiting.
  </check>

  <check id="S5" domain="Security" severity="High"
         applies_to="backend/src/products/ (image upload), backend/src/data_import/">
    FILE UPLOAD SAFETY — MIME type must be validated server-side, not from
    Content-Type header. Files stored outside web root with UUID filenames.

    Look for: new file upload handling that uses request.headers["content-type"]
              for MIME validation instead of python-magic.
    FAIL if: Content-Type header trusted for file type determination.
  </check>

  <check id="S6" domain="Security" severity="High"
         applies_to="backend/src/data_import/, backend/scripts/">
    CREDENTIAL ZERO-PERSISTENCE — source system credentials in migration/ETL
    code must never be logged, stored in DB, or echoed in error responses.

    Look for: new fields in migration models that store password/credentials,
              log calls that include credential variables,
              error handlers that return exception messages containing passwords.
    FAIL if: any of the above found in ETL or migration code.
  </check>

  <!-- ─── Applies to: financial / domain service files ─────────────────────── -->
  <check id="F1" domain="Security+Reliability" severity="Critical"
         applies_to="any backend/src/**/*.py touching monetary values">
    NO FLOAT FOR MONEY — all financial values must use Python Decimal.

    Look for: float( wrapping a price, quantity * 1.0, revenue / 100.0,
              Decimal(float_variable), round(price, 2) without Decimal
    Exceptions: ML/statistics code (Prophet df["y"], numpy arrays) —
                these are forecasting inputs, not stored financial values.
                Mark with # financial-float-ok if intentional.

    FAIL if: float() used to store, compute, or return any monetary value
             that will be written to the DB or returned in an API response.
  </check>

  <check id="F2" domain="Reliability" severity="High"
         applies_to="backend/src/pricing/, backend/src/fx/, backend/src/ai_engine/">
    ASYNC EVENT LOOP SAFETY — CPU-bound ML work must run in asyncio.to_thread().

    Look for: direct calls to Prophet().fit(), scipy.optimize.minimize(),
              numpy Monte Carlo loops, or any loop over > 1000 items
              that is NOT wrapped in asyncio.to_thread() or run_in_executor().

    FAIL if: any CPU-bound operation called directly in an async def function
             without asyncio.to_thread().
  </check>

  <check id="F3" domain="Reliability" severity="High"
         applies_to="backend/src/fx/, backend/src/ai_engine/">
    EXTERNAL API TIMEOUTS — all httpx calls must have an explicit timeout.

    Look for: httpx.AsyncClient() or httpx.get/post() without timeout= parameter,
              new external API calls added without timeout enforcement.

    FAIL if: any httpx call lacks an explicit timeout.
  </check>

  <check id="F4" domain="Reliability" severity="Medium"
         applies_to="backend/src/fx/, backend/src/ai_engine/">
    EXTERNAL API FALLBACK — outages must return degraded responses, not 500s.

    Look for: new httpx calls that propagate ConnectTimeout or HTTPStatusError
              directly to the caller without a fallback / cached value path.

    FAIL if: an external API exception can reach the router as an unhandled 500.
  </check>

  <!-- ─── Applies to: AI engine, pricing, cashflow ─────────────────────────── -->
  <check id="E1" domain="Ethical" severity="High"
         applies_to="backend/src/ai_engine/, backend/src/pricing/">
    AI CONFIDENCE DISCLOSURE — all recommendation and suggestion schemas must
    include data_points_used: int and confidence_reliable: bool.

    Look for: new Pydantic response schemas for recommendations or suggestions
              that lack these two fields.

    FAIL if: any new recommendation/suggestion schema omits confidence fields.
  </check>

  <check id="E2" domain="Ethical" severity="High"
         applies_to="backend/src/pricing/service.py">
    PRICING FLOOR — no price suggestion may be below FIFO landed cost.

    Look for: new price computation paths that do not check the result against
              the product's FIFO cost before returning.

    FAIL if: a price suggestion can be returned that is below landed cost
             without raising PricingSuggestionError.
  </check>

  <check id="E3" domain="Ethical" severity="Critical"
         applies_to="backend/src/ai_engine/ (anywhere Anthropic is called)">
    NO PII IN ANTHROPIC PROMPTS — customer names, emails, and phone numbers
    must never appear in Anthropic API prompt strings.

    Look for: new Anthropic client calls where the prompt string is built
              using customer.email, customer.full_name, customer.phone,
              or any variable that could contain customer PII.

    FAIL if: any new Anthropic prompt could include customer PII.
  </check>

  <check id="E4" domain="Ethical" severity="High"
         applies_to="backend/src/ai_engine/service.py, backend/src/cashflow/service.py">
    HUMAN REVIEW GATE — DELAY_PAYMENT and LIQUIDATE action types must have
    requires_human_review = True.

    Look for: new ActionType values with financial consequence that are NOT
              flagged requires_human_review = True.
              Also check: new recommendation generation paths for existing
              high-consequence types that omit the flag.

    FAIL if: DELAY_PAYMENT or LIQUIDATE (or any new high-consequence type)
             can be applied without requires_human_review = True.
  </check>

  <!-- ─── Applies to: auth domain ──────────────────────────────────────────── -->
  <check id="A1" domain="Security" severity="Critical"
         applies_to="backend/src/auth/">
    PASSWORD HASHING — bcrypt must be used. No MD5, SHA1, SHA256, or plaintext.

    Look for: new password hashing calls that do not use CryptContext(schemes=["bcrypt"]).
    FAIL if: any non-bcrypt hashing of a password field.
  </check>

  <check id="A2" domain="Security" severity="High"
         applies_to="backend/src/auth/router.py">
    COOKIE SECURITY — access_token cookie must be HttpOnly=True, SameSite=lax,
    Secure=True in non-development environments.

    Look for: new response.set_cookie() calls that omit httponly=True,
              or hardcode secure=True regardless of ENVIRONMENT.
    FAIL if: any cookie set without httponly=True.
  </check>

  <!-- ─── Applies to: data_import / ETL ───────────────────────────────────── -->
  <check id="M1" domain="Security+Reliability" severity="High"
         applies_to="backend/src/data_import/">
    MIGRATION_ID TAGGING — every table row inserted by a migration job must
    carry the migration_id UUID so rollback is possible.

    Look for: new INSERT paths in loader.py that do not set migration_id = job.id
              on the created ORM object.
    FAIL if: any loader insert omits migration_id.
  </check>

  <check id="M2" domain="Reliability" severity="High"
         applies_to="backend/src/data_import/">
    CONFIRMATION GATE — the Load phase must only be reachable via
    POST /import/jobs/{job_id}/confirm with approved=True.
    No internal service call should bypass this gate.

    Look for: new code paths that call loader.load() directly without
              checking job.status == "awaiting_confirmation".
    FAIL if: Load phase reachable without explicit approval.
  </check>

  <!-- ─── Always applies ────────────────────────────────────────────────────── -->
  <check id="G1" domain="Reliability" severity="Low"
         applies_to="any backend/src/**/*.py">
    NO PRINT STATEMENTS — use structlog logger.

    Look for: print( anywhere in src/ files.
    FAIL if: any print() found (structlog is the only permitted logging mechanism).
  </check>

  <check id="G2" domain="Reliability" severity="Medium"
         applies_to="any backend/src/**/*.py">
    STATIC BEFORE PARAMETERISED ROUTES — in FastAPI routers, literal path
    segments must be declared before {param} segments.

    Look for: new router definitions where a parameterised route (e.g. /{id})
              appears before a static route (e.g. /export, /summary) in the
              same router file.
    FAIL if: any static route declared after a parameterised route that
             would shadow it.
  </check>

  <check id="G3" domain="Reliability" severity="Medium"
         applies_to="any new SQLAlchemy Enum column">
    ENUM VALUES_CALLABLE — new Enum columns must use values_callable.

    Look for: mapped_column(Enum(MyEnum)) without
              values_callable=lambda x: [e.value for e in x]
    FAIL if: any new Enum column omits values_callable.
  </check>

  <check id="G4" domain="Reliability" severity="Medium"
         applies_to="any service returning ORM objects with relationships">
    SELECTINLOAD — relationships must be eagerly loaded before return.

    Look for: service functions that return ORM objects with relationship
              attributes accessed in the router/schema layer, without a
              selectinload() in the query.
    FAIL if: N+1 query pattern or lazy-load outside async context.
  </check>

</checks>

<output_format>
For each applicable check, report:

  [CHECK ID] [PASS|FAIL|NOT APPLICABLE]
  File: <filename>:<line> (only on FAIL)
  Issue: <one sentence describing the specific problem> (only on FAIL)
  Fix: <one sentence fix> (only on FAIL)

End with a summary:
  Total checks applicable: N
  PASS: N  |  FAIL: N  |  NOT APPLICABLE: N

  MERGE DECISION: READY TO OPEN PR / BLOCK — fix N issues first
</output_format>
```
