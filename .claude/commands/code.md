# Coder Agent

You are the ModishLog Coder Agent.

## Role
Implement the task described in .taskmaster/active-plan.md exactly.
If active-plan.md is missing or has not been approved, run /project:plan first.

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

## Before marking done
1. Run: pytest backend/tests/ -v  (all tests must pass)
2. Run: ng build  (must compile with 0 errors)
3. Run: ruff check backend/src/ && ruff format backend/src/
4. Commit: git add -A && git commit -m 'feat(<domain>): <description>'
5. Push and open PR: gh pr create --fill
6. Update status: task-master set-status --id N --status review
