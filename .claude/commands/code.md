# Coder Agent

You are the ModishLog Coder Agent.

## Role
Implement the task described in .taskmaster/active-plan.md exactly.
If active-plan.md is missing or has not been approved, run /project:plan first.

## TDD Workflow (MANDATORY)
Every feature MUST follow Test-Driven Development:

### Backend TDD
1. **Write tests FIRST** in `backend/tests/test_<domain>.py`
   - Write failing tests that define the expected behavior
   - Cover happy path, edge cases, and error cases
   - Run: `UPLOAD_DIR=/tmp/modishlog_uploads backend/.venv/bin/pytest <test_file> -v` to confirm tests FAIL
2. **Implement the feature** to make tests pass
   - Write minimum code to pass all tests
   - Run tests again to confirm they PASS
3. **Refactor** if needed while keeping tests green

### Frontend TDD
1. **Write component tests FIRST** or Playwright E2E tests in `frontend/e2e/`
   - For services: test API call shape and response mapping
   - For components: test rendering, user interactions, state changes
2. **Implement the component/service** to make tests pass
3. **Run `ng build`** to confirm compilation

### Test requirements per feature
- Every new backend function: at least 2 tests (happy path + error case)
- Every new endpoint: at least 1 endpoint-level test (status code + response shape)
- Every new frontend service method: interface defined before implementation
- Every new page component: Playwright E2E test for core user flow

## FastAPI coding rules
Structure: backend/src/<domain>/{router,service,models,schemas,exceptions}.py
- router.py  : thin -- parse request, call service, return response. No logic.
- service.py : all business logic. Always async. Injected via FastAPI Depends.
- models.py  : SQLAlchemy 2.0 -- use mapped_column() with Mapped[] type annotations.
- schemas.py : Pydantic v2 -- add model_config=ConfigDict(from_attributes=True)
               on all response schemas that map from ORM models.
- exceptions.py : domain-specific exceptions, each maps to an HTTP status code.
All routes prefixed: /api/v1/<resource>
All financial amounts: use Python Decimal. Map to NUMERIC(18,6) in PostgreSQL.
Background jobs (forecasting, email alerts): use FastAPI BackgroundTasks.
Logging: structlog.get_logger().info('event', key=value) -- never print().

### Route ordering
Static routes MUST come BEFORE parameterized routes to avoid conflicts:
```python
@router.get("/summary")     # static first
@router.get("/low-stock")   # static first
@router.get("/{item_id}")   # parameterized last
```

### Enum handling
When creating SQLAlchemy Enum columns for new enum types, use values_callable:
```python
role: Mapped[UserRole] = mapped_column(
    Enum(UserRole, values_callable=lambda x: [e.value for e in x]),
    default=UserRole.ADMIN,
)
```

### Relationship serialization
Always eager-load relationships before returning ORM objects for Pydantic serialization:
```python
result = await db.execute(
    select(Model).options(selectinload(Model.items)).where(Model.id == id)
)
return result.scalar_one()
```

### Derived/computed fields must not appear in Create schemas
If a field's true value can only be derived server-side from other state
(e.g. `has_variants` is really "does this product have any variants",
computed as a side effect of variant creation/deletion), do **not** also
accept it as an optional field on the `*Create` Pydantic schema "for
convenience." Pydantic silently drops unknown/extra fields by default, so a
caller (or an e2e seed helper) passing `has_variants: true` at creation time
gets no error and no effect -- the field is quietly ignored, and nothing
signals that the value never took. This is confusing to test against and to
extend later. Either add real support for setting it at creation time (with
validation), or leave it off the Create schema entirely so a stray field in
a request body is a Pydantic error, not a silent no-op.

### New rate-limited endpoints called repeatedly by e2e need e2e relaxation
If a new endpoint gets `@limiter.limit("N/minute")` and is expected to be
called more than N times across a full Playwright suite (registration,
login, any endpoint an e2e helper calls in `beforeEach`/`beforeAll`), add a
dedicated relaxation flag up front, following the existing
`E2E_RELAXED_LOGIN_RATE_LIMIT` / `E2E_AUTO_VERIFY_EMAIL` pattern in
`src/core/config.py`:
- A dedicated `bool` setting, default `False`.
- A `_xxx_rate_limit() -> str` function returning a relaxed limit when the
  flag is set, the normal limit otherwise.
- Set the flag to `"true"` **only** in `docker-compose.e2e.yml`, never tied
  to `ENVIRONMENT=test` -- the plain backend pytest CI job also sets
  `ENVIRONMENT=test`, and its own security regression tests specifically
  verify the strict limit is enforced there.
Skipping this means the endpoint works fine in isolation but fails
intermittently once a real e2e suite exercises it enough times in one run --
surfacing as a generic frontend error with the real cause (`429`) visible
only in backend logs, not in the Playwright output.

## Angular coding rules
- All components are standalone (no NgModule).
- Use ChangeDetectionStrategy.OnPush on every component.
- Use Angular Signals: input(), output(), computed(), signal().
- Use inject() function -- no constructor injection.
- HTTP calls only in services, never in components.
- Never use TypeScript 'any' -- define interfaces for all API responses.
- Error handling only in GlobalErrorInterceptor -- not in components.
- TailwindCSS for all styling -- no inline styles.
- Lazy-load all feature routes.

### `[ngModel]`/`[checked]` one-way binding does not auto-revert
A checkbox/input bound as `[ngModel]="expr"` (or `[checked]="expr"`, one-way,
no banana-in-a-box) plus a separate `(ngModelChange)`/`(change)` handler is a
common pattern for "intercept before committing" flows (e.g. show a confirm
dialog before actually toggling a destructive setting). **It silently breaks
if the cancel/revert path reassigns the SAME value the expression already
held** -- Angular's change-detection only re-writes the DOM when the bound
expression's value actually *changes* between checks. If the user's native
click already flipped the checkbox and your cancel handler sets the backing
signal/field back to the value it logically "was" (but which the CD cycle
already considers unchanged, since nothing else touched it), the view never
gets told to re-sync and stays visually wrong even though internal state is
correct. Symptom: `toBeChecked()`/`not.toBeVisible()` assertions fail in e2e
tests immediately after a cancel action, with no error anywhere.
Fix: add a template ref (`#myInput`) + `viewChild<ElementRef>()`, and in the
cancel/revert handler set `el.nativeElement.checked = value` directly,
alongside the signal update (which is still needed for internal state).
Prefer this pattern from the start for any checkbox gating a destructive
action behind a confirm dialog -- don't wait to discover it via a flaky test.

## Git workflow (MANDATORY)
1. Create branch: `git checkout -b feat/<task-id>-<description> main`
2. Write tests first (TDD)
3. Implement feature
4. Run: `UPLOAD_DIR=/tmp/modishlog_uploads backend/.venv/bin/pytest backend/tests/ -v`
5. Run: `ng build` (0 errors)
6. Run: `ruff check backend/src/ && ruff format backend/src/`
7. Commit: `git add <specific files> && git commit -m 'feat(<domain>): <description>'`
8. Push: `git push -u origin <branch>`
9. PR: `gh pr create --fill`
10. Review: run /review agent on the PR
11. Update status: `task-master set-status --id N --status done`

## Before marking done checklist
- [ ] Tests written BEFORE implementation (TDD)
- [ ] All new functions have tests (happy path + error case)
- [ ] pytest passes (all tests)
- [ ] ng build compiles (0 errors)
- [ ] ruff check passes
- [ ] Committed on feature branch
- [ ] PR opened and reviewed
- [ ] Task status updated
