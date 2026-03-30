# ModishLog -- Project Master Instructions

## What this project is
ModishLog is a smart business management platform for everyday traders and SMB
owners — tracking sales, managing inventory, understanding profit and loss,
getting pricing insights and AI-driven buying/selling suggestions.
Full requirements are in .taskmaster/docs/prd.txt.

## Stack
- Backend  : Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + Alembic + PostgreSQL
- Frontend : Angular 17 (standalone components, Signals) + TailwindCSS + PrimeNG
- AI/ML    : Prophet + NumPy/SciPy (Monte Carlo) + scikit-learn
- Auth     : JWT (python-jose) + bcrypt (passlib)
- Infra    : Docker + Docker Compose

## Rules that apply to every task (non-negotiable)
1. Use async/await for ALL database operations and external API calls
2. Write a test for every new function BEFORE marking any task done
3. Run `pytest backend/tests/` and confirm it passes before committing
4. Run `ng build` and confirm it compiles before committing
5. Never commit .env files, secrets, or API keys to git
6. Never use print() -- use structlog logger from core/logging.py
7. Never write raw SQL -- use SQLAlchemy ORM only
8. All financial values must use Python Decimal, never float

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
