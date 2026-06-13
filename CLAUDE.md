# ModishLog -- Project Master Instructions

## What this project is
ModishLog is a smart business management platform for everyday traders and SMB
owners — tracking sales, managing inventory, understanding profit and loss,
getting pricing insights and AI-driven buying/selling suggestions.
Full requirements are in .taskmaster/docs/prd.txt.

## Stack
- Backend  : Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + Alembic + PostgreSQL
- Frontend : Angular 21 (standalone components, Signals) + TailwindCSS v4 + PrimeNG v21
- AI/ML    : Prophet + NumPy/SciPy (Monte Carlo) + scikit-learn
- Auth     : JWT (python-jose) + bcrypt (passlib)
- Infra    : Docker + Docker Compose

## Rules that apply to every task (non-negotiable)
1. Use async/await for ALL database operations and external API calls
2. **TDD: Write tests BEFORE implementation** -- every new backend function
   needs at least 2 tests (happy path + error case) written FIRST
3. **TDD: Write E2E tests** -- every new frontend page/feature needs a
   Playwright E2E test in frontend/e2e/
4. Run `docker compose exec backend pytest tests/` and confirm it passes before committing
5. Run `ng build` and confirm it compiles before committing
6. Never commit .env files, secrets, or API keys to git
7. Never use print() -- use structlog logger from core/logging.py
8. Never write raw SQL -- use SQLAlchemy ORM only
9. All financial values must use Python Decimal, never float
10. Static routes BEFORE parameterized routes in FastAPI routers
11. Use `values_callable` on new SQLAlchemy Enum columns
12. Always `selectinload()` relationships before returning ORM objects

## Project structure
- Backend domain modules: backend/src/<domain>/
  Each domain: router.py  service.py  models.py  schemas.py  exceptions.py
- Frontend features: frontend/src/app/features/<feature>/
  Each feature: components/  services/  models/  pages/

## Git workflow
- Branch format : feat/<task-id>-<short-description>
- Commit format : feat(<domain>): <present-tense description>
- Always create branch from main before starting each task
- Open a PR after every task -- never push directly to main
- PRs require passing CI (pytest + ng build) before merge

## Task management
- Task list: .taskmaster/tasks/tasks.json
- Get next task: task-master next
- Mark done after tests pass: task-master set-status --id N --status done

## Cost controls
- Use Sonnet for ALL implementation tasks (default in settings.json)
- Use Opus ONLY when running /project:plan
- Always /clear between unrelated tasks
- Use plan mode (Shift+Tab twice) before tasks touching 3+ files
- If session token cost exceeds USD 2 run /clear and restart with smaller scope
