
FXWise
Automated Build Setup Guide

Claude Code CLI  +  TaskMaster AI  +  GitHub Automation
FastAPI (Python)  +  Angular 17  +  PostgreSQL

March 2026

How to use this guide



This document is your complete, end-to-end blueprint for automating the FXWise build. Every file you need is shown in full. Every terminal command is exact. Read it fully before starting, then execute it top to bottom.

Box type
What it means
HUMAN ACTION REQUIRED (red border)
You must do this yourself -- Claude cannot do it for you
CHECKPOINT (green border)
Verify this passes before moving to the next step
IMPORTANT (amber border)
Read carefully -- skipping this causes downstream failures
INFO (blue border)
Context or explanation -- no action needed
Code block (dark background)
Copy and paste exactly as shown into your terminal or file


IMPORTANT
Cost overview: This setup uses Claude Sonnet 4.6 for all implementation tasks.
Opus is used only for the Planner agent. A full Stage A build (~21 tasks) costs
approximately USD 12-22 via pay-as-you-go API. A Claude Max subscription at USD 100/mo
makes Stage A effectively free and is recommended if you plan to iterate.
All cost-control measures are baked into the config files in Step 3.



Step 1 -- Prerequisites and accounts



Complete everything in this section before running any build command. Each item is marked with who sets it up.

1.1  Tools to install on your machine
HUMAN ACTION REQUIRED
Install ALL of the following before proceeding:

  Node.js 20+ (LTS)         https://nodejs.org
  Python 3.11+              https://python.org
  Git 2.40+                 https://git-scm.com
  Docker Desktop            https://docker.com/products/docker-desktop
  GitHub CLI (gh)           https://cli.github.com
  Angular CLI               npm install -g @angular/cli
  Claude Code CLI           npm install -g @anthropic-ai/claude-code
  TaskMaster AI             npm install -g task-master-ai


1.2  Accounts to create or log in to
HUMAN ACTION REQUIRED
You need accounts on the following platforms:

  Anthropic Console     https://console.anthropic.com   (required: API key)
  GitHub                https://github.com              (required: repo + Actions)

  Perplexity API        https://perplexity.ai           (optional: TaskMaster research)


1.3  API keys to collect
HUMAN ACTION REQUIRED
Anthropic Console -> API Keys -> Create Key:
  Copy your ANTHROPIC_API_KEY  (format: sk-ant-api03-...)

Perplexity (optional but recommended for TaskMaster research tasks):
  Copy your PERPLEXITY_API_KEY

Keep these ready -- you will paste them into .env in Step 3.


1.4  Authenticate both CLIs
# Authenticate Claude Code CLI
claude login
 
# Authenticate GitHub CLI
gh auth login
# Choose: GitHub.com -> HTTPS -> Login with browser
 
# Verify both work
claude --version
gh auth status


CHECKPOINT
claude --version returns a version number
gh auth status shows:  Logged in to github.com as <your-username>



Step 2 -- GitHub repository setup



Claude Code raises PRs, reviews code, and merges branches. This requires a GitHub repo with branch protection and Actions enabled. The commands below set this up in under five minutes.

2.1  Create the repository and protect main
HUMAN ACTION REQUIRED
Run these commands in your terminal:


# Create private repo and clone it
gh repo create fxwise --private --clone
cd fxwise
 
# Create an initial commit so main branch exists
echo "# FXWise" > README.md
git add README.md
git commit -m "chore: initial commit"
git push -u origin main
 
# Protect main branch: require PR + passing CI before merge
gh api repos/:owner/fxwise/branches/main/protection \
  --method PUT \
  --field "required_pull_request_reviews[required_approving_review_count]=1" \
  --field "required_status_checks[strict]=true" \
  --field "required_status_checks[contexts][]=backend-tests" \
  --field "required_status_checks[contexts][]=frontend-build" \
  --field "enforce_admins=false" \
  --field "allow_force_pushes=false"
 
# Add repository secrets for CI/CD
gh secret set ANTHROPIC_API_KEY
# (Paste your key when prompted)
gh secret set POSTGRES_PASSWORD --body "fxwise_dev_2026"
gh secret set SECRET_KEY --body "$(openssl rand -hex 32)"


2.2  Repository folder structure (Claude will build this)
This is the full target structure. Do not create it manually -- Claude scaffolds it in Steps 4 and 6. It is shown here so you understand the layout before configuring the agents.

fxwise/
|-- .claude/
|   |-- settings.json          # Claude Code config + cost controls
|   `-- commands/              # Agent slash commands (one file per role)
|       |-- plan.md
|       |-- code.md
|       |-- review.md
|       |-- design.md
|       `-- test.md
|-- .taskmaster/
|   |-- config.json            # TaskMaster model config
|   `-- docs/
|       `-- prd.txt            # FXWise PRD (you paste here in Step 5)
|-- .github/
|   `-- workflows/
|       |-- backend-tests.yml
|       `-- frontend-build.yml
|-- backend/                   # FastAPI (Python)
|   |-- src/
|   |   |-- auth/
|   |   |-- orders/
|   |   |-- sales/
|   |   |-- inventory/
|   |   |-- fx/
|   |   |-- cashflow/
|   |   |-- pricing/
|   |   |-- ai_engine/
|   |   `-- core/
|   |-- alembic/
|   |-- tests/
|   |-- Dockerfile
|   `-- requirements.txt
|-- frontend/                  # Angular 17
|   |-- src/app/
|   |   |-- core/              # services, guards, interceptors
|   |   |-- shared/            # reusable components
|   |   |-- features/          # dashboard, sales, orders, fx, cashflow, pricing
|   |   `-- layout/            # shell, sidebar, topbar
|   `-- Dockerfile
|-- CLAUDE.md                  # Master AI instruction file
|-- AGENTS.md                  # Agent role definitions
|-- docker-compose.yml
`-- .env.example



Step 3 -- Create all configuration files



Create every file below exactly as shown. Run the mkdir command first, then create each file using your editor or by running the code blocks in your terminal.

mkdir -p .claude/commands
mkdir -p .taskmaster/docs
mkdir -p .github/workflows


3.1  CLAUDE.md  (root of project)
IMPORTANT
This file is loaded into EVERY Claude Code session. Keep it under 500 lines.
Only put rules that apply to ALL tasks here. Agent-specific rules go in
.claude/commands/ files (Section 3.3) -- those are loaded on demand only.


Create file: CLAUDE.md
# FXWise -- Project Master Instructions
 
## What this project is
FXWise is an AI-powered import and trade intelligence platform for Nigerian
importers managing FX exposure across 4-6 month supply lead times.
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


3.2  .claude/settings.json  (cost optimisation config)
Create file: .claude/settings.json
{
  "model": "claude-sonnet-4-6",
  "env": {
    "MAX_THINKING_TOKENS": "8000",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "75",
    "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1"
  },
  "autoApprove": [
    "Bash(pytest*)",
    "Bash(ng build*)",
    "Bash(ng test*)",
    "Bash(ruff*)",
    "Bash(git add*)",
    "Bash(git commit*)",
    "Bash(git checkout*)",
    "Bash(git push*)",
    "Bash(task-master*)",
    "Read(*)",
    "Write(*)",
    "Edit(*)"
  ],
  "denyList": [
    "Bash(rm -rf*)",
    "Bash(*prod*)",
    "Bash(curl * | bash*)",
    "Read(.env*)",
    "Write(.env*)"
  ]
}


COST CONTROL -- what each setting does
MAX_THINKING_TOKENS 8000 -- cuts extended-thinking cost by 75% vs the 31k default.
CLAUDE_AUTOCOMPACT_PCT_OVERRIDE 75 -- compacts at 75% context, not 95%.
  This prevents expensive tail-of-context token bloat.
DISABLE_NON_ESSENTIAL_MODEL_CALLS 1 -- kills background suggestion/tip API calls.
autoApprove list -- removes permission prompts for safe routine operations.
denyList -- prevents Claude from touching production, secrets, or destructive commands.


3.3  Agent slash command files  (.claude/commands/)
Each file creates a /project:<name> command inside Claude Code. Commands are loaded ON DEMAND -- they cost zero tokens until called. This is the correct pattern for role-specific, context-heavy instructions.

File: .claude/commands/plan.md  --  Planner Agent
# Planner Agent
 
You are the FXWise Planner Agent.
 
## Role
Analyse the codebase and current task list to produce a detailed implementation
plan before any code is written. You do NOT write implementation code.
Your output is a plan file at .taskmaster/active-plan.md
 
## Model
Switch to claude-opus-4-6 for this command only. Switch back to claude-sonnet-4-6
when the plan is complete and approved.
 
## Process
1. Run: task-master next  -- identify the current recommended task
2. Run: task-master analyze-complexity  -- get complexity scores
3. For any task with complexity >= 7 run: task-master expand --id N
4. Write .taskmaster/active-plan.md with:
     - Task ID and title
     - Files to create or modify (with full paths)
     - Step-by-step approach
     - Test strategy (what to test, what fixtures are needed)
     - Estimated token budget
5. Present the plan and STOP. Wait for human approval.
   Do not write any code until the human types 'Plan approved'.
 
## Planning rules
- Use plan mode (Shift+Tab) before each response
- Reference specific file paths and line numbers
- If a dependency task is not done, flag it as a blocker
- Prefer the simplest implementation that satisfies the acceptance criteria


File: .claude/commands/code.md  --  Coder Agent
# Coder Agent
 
You are the FXWise Coder Agent.
 
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


File: .claude/commands/review.md  --  Reviewer Agent
# Reviewer Agent
 
You are the FXWise Code Reviewer Agent.
 
## Role
Review all code changes on the current branch against the standards in CLAUDE.md.
You are the quality gate. Do not approve unless ALL checklist items pass.
 
## Review checklist
 
Security:
  [ ] No hardcoded secrets, passwords, or API keys
  [ ] All endpoints that modify data require authentication
  [ ] Pydantic validates all input before it reaches the service layer
  [ ] No raw SQL anywhere -- ORM used throughout
 
Correctness:
  [ ] Financial calculations use Decimal, not float
  [ ] All database operations are async
  [ ] Error cases return correct HTTP status codes
  [ ] Tests cover the happy path AND at least 2 error cases per endpoint
 
Code quality:
  [ ] No business logic in router.py files
  [ ] No direct DB calls in routers -- always via service layer
  [ ] Angular components are under 200 lines (extract if larger)
  [ ] No TypeScript 'any' types
  [ ] No unused imports
 
## Process
1. Run: git diff main...HEAD  -- examine all changed files
2. Apply checklist above to each changed file
3. Write findings to .taskmaster/review-<branch-name>.md
4. If ALL items pass:
   gh pr review --approve --body 'LGTM -- all checklist items passed'
5. If issues found:
   gh pr review --request-changes --body-file .taskmaster/review-<branch>.md
6. Update task: task-master set-status --id N --status done OR in-progress


File: .claude/commands/design.md  --  Designer Agent
# Designer Agent
 
You are the FXWise UI/UX Designer Agent.
 
## Role
Produce Angular component specifications and TailwindCSS layouts for FXWise.
Output implementation-ready component templates, not mockups.
 
## FXWise design system
Primary   : #1F4E79  (deep navy)
Secondary : #2E75B6  (mid blue)
Success   : #1A7A4A  (green)
Warning   : #D97706  (amber)
Danger    : #C0392B  (red)
Background: #F8FAFC
Surface   : #FFFFFF
Text      : #1E293B
Muted     : #64748B
 
## Standard components
MetricCard  -- title, large value, unit, trend arrow, colour-coded border
AlertBanner -- severity-coloured left border, icon, message, dismiss button
DataTable   -- sticky header, alternating rows, sort indicators, pagination
ChartPanel  -- title, Chart.js chart, date-range selector
StatusBadge -- pill, colour-coded by severity
 
## Responsive breakpoints
Mobile  (<768px) : single column, bottom tab nav, horizontal scroll for tables
Tablet  (768px+) : 2-column grid, side nav
Desktop (1200px+): 3-4 column grid, all panels visible
 
## Output format
For each component produce:
  1. Angular standalone component template (HTML + Tailwind classes)
  2. TypeScript input/output interface definition
Write output to frontend/src/app/shared/components/<name>/


File: .claude/commands/test.md  --  Test Agent
# Test Agent
 
You are the FXWise Test Agent.
 
## Role
Write and run comprehensive tests. Target: 80% line coverage across backend.
 
## Backend test rules (pytest + pytest-asyncio)
- Use httpx AsyncClient (not TestClient) for all API endpoint tests
- Fixtures in conftest.py: db_session, auth_headers, test_product, test_user
- Financial tests MUST include: Decimal precision, zero balances, extreme FX rates
- Every service function: 1 happy path + minimum 2 error path tests
- Use factory-boy for test data factories
 
## Frontend tests (Jasmine + Cypress)
- Unit tests for all Angular services
- Component tests for all dashboard components
- Cypress e2e for critical flows: login, sales entry, order creation
 
## After writing tests
1. Run: pytest backend/tests/ -v --cov=src --cov-report=term-missing
2. If coverage < 80% on a module, write more tests before marking done
3. Run: ng test --watch=false
4. Report coverage summary in the task notes


3.4  .taskmaster/config.json  (TaskMaster AI config)
ZERO EXTRA COST -- TaskMaster via Claude Code
Using 'claude-code' as the provider routes TaskMaster's AI calls through your
Claude Code subscription -- no separate API key or extra billing required.
Sonnet handles all task management; Opus is reserved for complexity analysis.


Create file: .taskmaster/config.json
{
  "models": {
    "main": {
      "provider": "claude-code",
      "modelId": "sonnet",
      "maxTokens": 64000,
      "temperature": 0.2
    },
    "research": {
      "provider": "claude-code",
      "modelId": "opus",
      "maxTokens": 32000,
      "temperature": 0.1
    },
    "fallback": {
      "provider": "claude-code",
      "modelId": "sonnet",
      "maxTokens": 64000,
      "temperature": 0.2
    }
  },
  "global": {
    "logLevel": "info",
    "debug": false,
    "defaultNumTasks": 12,
    "defaultSubtasks": 5,
    "defaultPriority": "medium",
    "projectName": "FXWise"
  },
  "claudeCode": {}
}


3.5  AGENTS.md  (agent roster reference)
Create file: AGENTS.md
# FXWise -- Agent Roster
 
Each agent is a Claude Code slash command in .claude/commands/.
Invoke with /project:<name> from inside a Claude Code session.
 
| Agent    | Command          | Model  | Purpose                                    |
|----------|-----------------|--------|---------------------------------------------|
| Planner  | /project:plan   | Opus   | Task breakdown, architecture, active-plan.md|
| Coder    | /project:code   | Sonnet | Implement, test, commit, open PR            |
| Reviewer | /project:review | Sonnet | Code review, PR approval, quality gate      |
| Designer | /project:design | Sonnet | UI component specs, Tailwind layouts        |
| Tester   | /project:test   | Sonnet | Test writing, coverage analysis             |
 
## Standard workflow per task
1. /project:plan   -- writes .taskmaster/active-plan.md -- HUMAN APPROVES
2. /project:code   -- implements plan, runs tests, opens PR
3. /project:review -- reviews PR, approves or requests changes
4. Human merges PR on GitHub
5. task-master set-status --id N --status done
 
## When to use each agent
Starting a new module?     -- planner first, then coder
Implementing a known task? -- coder directly
PR is waiting for review?  -- reviewer
Test coverage is low?      -- tester
Building a dashboard page? -- designer first, then coder


3.6  docker-compose.yml
Create file: docker-compose.yml
version: '3.9'
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: fxwise
      POSTGRES_USER: fxwise
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-fxwise_dev}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports: ['5432:5432']
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U fxwise']
      interval: 5s
      retries: 5
 
  redis:
    image: redis:7-alpine
    ports: ['6379:6379']
 
  backend:
    build: { context: ./backend, dockerfile: Dockerfile }
    environment:
      DATABASE_URL: postgresql+asyncpg://fxwise:${POSTGRES_PASSWORD:-fxwise_dev}@db/fxwise
      REDIS_URL: redis://redis:6379
      SECRET_KEY: ${SECRET_KEY:-dev-secret-change-in-production}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      ENVIRONMENT: development
    ports: ['8000:8000']
    depends_on: { db: { condition: service_healthy } }
    volumes: ['./backend:/app']
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
 
  frontend:
    image: node:20-alpine
    working_dir: /frontend
    volumes: ['./frontend:/frontend']
    ports: ['4200:4200']
    command: npm start
    depends_on: [backend]
 
volumes:
  postgres_data:


3.7  .env.example  (commit to git -- never .env itself)
Create file: .env.example
# FXWise environment variables
# Copy to .env and fill in real values. NEVER commit .env to git.
 
POSTGRES_PASSWORD=fxwise_dev
SECRET_KEY=generate-with-openssl-rand-hex-32
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
 
ANTHROPIC_API_KEY=sk-ant-...
 
FX_API_KEY=
FX_API_URL=https://api.example.com/fx
 
PERPLEXITY_API_KEY=
 
ENVIRONMENT=development
LOG_LEVEL=info


3.8  .gitignore
Create file: .gitignore
.env
.env.local
.env.production
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
htmlcov/
.coverage
venv/
.venv/
node_modules/
dist/
.angular/
postgres_data/
.vscode/settings.json
.idea/
.taskmaster/active-plan.md
.taskmaster/review-*.md


3.9  GitHub Actions workflows
Create file: .github/workflows/backend-tests.yml
name: backend-tests
on:
  pull_request:
    paths: ['backend/**']
 
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: fxwise_test
          POSTGRES_USER: fxwise
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-retries 5
        ports: ['5432:5432']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11', cache: pip }
      - run: pip install -r backend/requirements.txt
      - run: ruff check backend/src/
      - run: pytest backend/tests/ -v --cov=src --cov-fail-under=70
        env:
          DATABASE_URL: postgresql+asyncpg://fxwise:test@localhost/fxwise_test
          SECRET_KEY: test-secret-key
          ENVIRONMENT: test


Create file: .github/workflows/frontend-build.yml
name: frontend-build
on:
  pull_request:
    paths: ['frontend/**']
 
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: npm,
                cache-dependency-path: frontend/package-lock.json }
      - run: npm ci
        working-directory: frontend
      - run: ng build --configuration production
        working-directory: frontend
      - run: ng test --watch=false --browsers=ChromeHeadless
        working-directory: frontend



Step 4 -- Scaffold the boilerplate



The official FastAPI template uses React. We replace React with Angular 17 and adapt the backend structure to FXWise's domain-based module layout. Claude handles all scaffolding -- your job is to confirm each step passes.

4.1  Scaffold the FastAPI backend
Open Claude Code in the project root, then type the following prompt:
cd fxwise
claude


PROMPT TO TYPE IN CLAUDE CODE
In the Claude Code session, type this prompt:

  Scaffold the FXWise FastAPI backend using the domain-based structure in CLAUDE.md.

  Create these files:
  1. backend/requirements.txt   (all dependencies -- see Appendix A for full list)
  2. backend/src/main.py        (FastAPI app with lifespan, CORS, routers included)
  3. backend/src/core/config.py (pydantic-settings Settings class, reads from .env)
  4. backend/src/core/database.py (async SQLAlchemy engine and session factory)
  5. backend/src/core/logging.py  (structlog configuration)
  6. backend/src/core/security.py (JWT encode/decode, password hash/verify)
  7. backend/Dockerfile
  8. backend/alembic.ini and backend/alembic/env.py

  Create skeleton files for all 8 domains (auth, orders, sales, inventory,
  fx, cashflow, pricing, ai_engine) with router.py, service.py, models.py,
  schemas.py, exceptions.py -- placeholder TODOs, no implementation yet.

  Run: ruff check backend/src/  -- all files must pass.
  Run: python -c 'from src.main import app'  -- must import without error.


4.2  Scaffold the Angular frontend
Open a second Claude Code session (new terminal tab), then type:
cd fxwise
claude


PROMPT TO TYPE IN SECOND CLAUDE CODE SESSION
In the second Claude Code session, type this prompt:

  Scaffold the FXWise Angular 17 frontend.

  Step 1 -- Generate app:
    ng new frontend --standalone --routing --style=css --skip-git

  Step 2 -- Install dependencies:
    npm install tailwindcss @tailwindcss/forms primeng primeicons
    npm install -D @types/node

  Step 3 -- Configure TailwindCSS:
    Create tailwind.config.js with content paths for src/**/*.{html,ts}
    Add @tailwind directives to src/styles.css

  Step 4 -- Create core module structure:
    core/services/api.service.ts      (HttpClient wrapper with base URL from env)
    core/services/auth.service.ts     (login, logout, token storage in localStorage)
    core/guards/auth.guard.ts         (redirects to /login if no token)
    core/interceptors/auth.interceptor.ts   (adds Bearer token to requests)
    core/interceptors/error.interceptor.ts  (handles 401/403/500 globally)

  Step 5 -- Create feature skeleton folders:
    features/dashboard/  features/sales/  features/orders/
    features/fx/  features/cashflow/  features/pricing/
    (each has components/ services/ models/ pages/ subdirs)

  Step 6 -- Create layout components:
    layout/shell/  layout/sidebar/  layout/topbar/

  Step 7 -- Create shared components:
    shared/components/metric-card/
    shared/components/alert-banner/
    shared/components/data-table/
    shared/components/status-badge/

  All components standalone. Use Angular Signals for state.
  API base URL: http://localhost:8000/api/v1 (from environment.ts).
  End by running: ng build  -- must complete with 0 errors.


4.3  Verify the scaffold
CHECKPOINT
docker compose up  starts with no errors
http://localhost:8000/docs  loads the FastAPI OpenAPI UI
http://localhost:4200  loads the Angular app
pytest backend/tests/  runs (may have 0 tests -- that is OK at this stage)
ng build  compiles with 0 errors
git status  shows all new files; commit everything to main



Step 5 -- Initialise TaskMaster and generate tasks



5.1  Paste the PRD
HUMAN ACTION REQUIRED
Open the file .taskmaster/docs/prd.txt
Paste the FULL TEXT of the FXWise PRD (the document created in the earlier session).
Save the file. Do not rename it.

This is the single most important input -- TaskMaster parses it to generate
all tasks with correct dependencies. The more complete the PRD, the better the tasks.


5.2  Initialise and parse in Claude Code
# In Claude Code (claude command in project root)
 
> Initialise TaskMaster AI for this project and parse the PRD.
> Run: task-master init
> Then: task-master parse-prd .taskmaster/docs/prd.txt
> Then show me the full task list: task-master list


IMPORTANT
Known issue: Claude Code may show a JSON parsing error on large PRDs.
Workaround: Run 'task-master parse-prd .taskmaster/docs/prd.txt' from your
TERMINAL DIRECTLY (not inside Claude Code). Then return to Claude Code.
Run task-master list to confirm tasks were generated.


5.3  Analyse complexity and expand complex tasks
> Run: task-master analyze-complexity
> For every task with complexity score >= 7, expand it:
> Run: task-master expand --id N  for each such task
> Show me the updated task list with all subtasks


5.4  Review and approve the task list
HUMAN ACTION REQUIRED
Open .taskmaster/tasks/tasks.json and review the generated tasks.

Check for:
  - All 8 functional modules from the PRD are represented
  - Dependencies look correct (auth before orders, orders before FX engine, etc.)
  - Stage A Must Have items are ranked highest priority

Adjust priorities if needed:
  task-master update --id N --priority high

When satisfied, proceed to Step 6.



Step 6 -- The automation loop



This is the core workflow. Every task follows the same five-step pattern. You run the loop manually but each step is Claude-driven. Repeat for all 21 Stage A tasks.

6.1  Standard loop (repeat for every task)
Step
You type
Claude does
Human input?
1. Get next task
task-master next
Shows next recommended task with full context
Read and understand
2. Plan
/project:plan
Analyses task, writes .taskmaster/active-plan.md
Type 'Plan approved' OR 'Revise: <feedback>'
3. Code
/project:code
Creates branch, implements, runs tests, opens PR
None
4. Review
/project:review (new session, /clear first)
Reviews PR, approves or requests changes
Merge PR on GitHub
5. Mark done
task-master set-status --id N --status done
Updates task state, ready for next
None


IMPORTANT
Always /clear between step 3 (code) and step 4 (review).
Never carry the coding context into the review session --
the reviewer must read the diff fresh, not from the coder's memory.


6.2  First task walkthrough  (auth module, ST-101 and ST-102)
Use this first task to verify the full loop works end to end before continuing.
# Terminal 1 -- Claude Code session
cd fxwise && claude
 
# Step 1: get the task
> task-master next
 
# Step 2: plan
> /project:plan
# Read active-plan.md carefully
# Type: Plan approved
 
# Step 3: code (Claude runs automatically)
> /project:code
# Claude creates branch, implements JWT auth, writes tests, opens PR
 
# Step 4: review (NEW session -- open new terminal)
cd fxwise && claude
> /clear
> /project:review
# If reviewer approves: merge PR on GitHub web UI
 
# Step 5: mark done
> task-master set-status --id 1 --status done


6.3  Full Stage A task sequence (~21 tasks)
#
Task / module
Agents
Est. tokens
1
JWT auth + user model (ST-101, ST-102)
planner + coder + reviewer
~45k
2
DB schema + Alembic migrations (all entities)
planner + coder + reviewer
~65k
3
Product and inventory CRUD endpoints
coder + reviewer + tester
~38k
4
Daily sales entry API (ST-301 to ST-303)
coder + reviewer + tester
~42k
5
Inventory auto-depletion and reorder trigger
coder + reviewer + tester
~36k
6
Order management CRUD + status workflow (ST-501, ST-502)
coder + reviewer
~45k
7
FX data ingestion service + exposure engine (ST-601 to ST-603)
planner + coder + reviewer
~58k
8
Cashflow projection + loan module (ST-701 to ST-703)
planner + coder + reviewer
~58k
9
Prophet + Monte Carlo forecasting service
planner + coder + reviewer + tester
~72k
10
Demand elasticity + pricing module (ST-801, ST-802)
planner + coder + reviewer
~52k
11
AI recommendation engine (ST-901, ST-902)
planner + coder + reviewer
~62k
12
Angular shell, routing, auth guard, lazy routes
designer + coder + reviewer
~42k
13
Shared components: MetricCard, AlertBanner, DataTable, StatusBadge
designer + coder
~38k
14
Liquidity risk dashboard page
designer + coder + reviewer
~48k
15
Daily sales entry view
designer + coder + reviewer
~36k
16
FX exposure dashboard page
designer + coder + reviewer
~42k
17
Order detail and reorder view
designer + coder + reviewer
~46k
18
Cashflow projection view + scenario toggle
designer + coder + reviewer
~50k
19
Portfolio margin and pricing view
designer + coder + reviewer
~42k
20
Settings view + API key configuration
coder + reviewer
~26k
21
End-to-end integration tests + Docker Compose wiring
tester + reviewer
~52k


ESTIMATED COST FOR STAGE A
Estimated total tokens for Stage A: ~900k input + ~260k output.
At Sonnet 4.6 pricing (~USD 3 per MTok input, USD 15 per MTok output):
  Input:  900k * 0.000003  = ~USD 2.70
  Output: 260k * 0.000015  = ~USD 3.90
  Total API cost estimate  : ~USD 6-10
Add ~USD 4-8 for Opus planning sessions.
Grand total Stage A via API: USD 10-18.
With Claude Max (USD 100/month): effectively free.



Step 7 -- Cost optimisation cheat sheet



Apply these consistently. Combined, they reduce token usage by 60-70%.

7.1  Model selection
Task type
Model
Why
Architecture planning
Opus (/project:plan only)
Complex reasoning; prevents rework that costs more
Implementation
Sonnet (default)
Excellent coder; 10x cheaper than Opus
Code review
Sonnet
Checklist matching -- no need for Opus reasoning
Test writing
Sonnet
Template-driven and deterministic
UI component specs
Sonnet
Patterns well-defined in design.md


7.2  Context management rules
/clear at the start of EVERY new task -- never carry context between tasks
/clear (not /compact) when switching between backend and frontend work
Reference files by path, never by embedding: say 'see backend/src/auth/service.py' not paste the file
One task per session -- never batch two unrelated tasks in one Claude Code session
Plan mode (Shift+Tab twice) before any task touching 3+ files
CLAUDE.md stays under 500 lines -- agent-specific rules live in .claude/commands/ files

7.3  Prompt quality rules
Bad: 'improve the auth module'
Good: 'add refresh token rotation to backend/src/auth/service.py -- see ST-101 in prd.txt'
Bad: 'fix tests'
Good: 'pytest fails on test_fx_exposure.py line 47 -- TypeError: Decimal expected. Fix it.'
Always include: task ID, specific file paths, exact acceptance criterion from PRD
Paste error messages directly -- never describe errors in words

7.4  Monitoring token usage
# Install usage tracker
npm install -g ccusage
 
# Daily cost breakdown
ccusage daily
 
# Live 5-hour billing window (run in second terminal during sessions)
ccusage blocks --live
 
# Check cost mid-session inside Claude Code
/cost
 
# If session cost exceeds USD 2 -- stop, /clear, restart with smaller scope



Appendix A -- FastAPI coding standards



These standards are sourced from the FastAPI official documentation and the widely-cited zhanymkanov/fastapi-best-practices repository. They are embedded verbatim in the Coder Agent (Section 3.3).

A.1  Domain-based project structure (Netflix Dispatch pattern)
backend/src/
|-- main.py                  # FastAPI app, lifespan, CORS, include_router calls
|-- core/
|   |-- config.py            # pydantic-settings BaseSettings (reads .env)
|   |-- database.py          # async SQLAlchemy engine, get_db Depends
|   |-- security.py          # create_access_token, verify_password, get_current_user
|   `-- logging.py           # structlog setup
|-- auth/
|   |-- router.py            # POST /api/v1/auth/login, /refresh, /logout
|   |-- service.py           # authenticate_user, create_tokens, revoke_token
|   |-- models.py            # User SQLAlchemy model
|   |-- schemas.py           # LoginRequest, TokenResponse Pydantic models
|   |-- dependencies.py      # get_current_user Depends function
|   `-- exceptions.py        # InvalidCredentials, TokenExpired
|-- fx/                      # same pattern for every domain
|-- orders/
|-- sales/
|-- inventory/
|-- cashflow/
|-- pricing/
`-- ai_engine/


A.2  Key rules with rationale
async everywhere: all route handlers and service methods use async def
Thin routers: route handler = parse input + call one service method + return response. Nothing else.
Pydantic v2: use model_config = ConfigDict(from_attributes=True) on ORM response schemas
SQLAlchemy 2.0: use mapped_column() with Mapped[] type annotations, not old Column()
Dependency injection: db session via Depends(get_db), never create sessions in service layer
Financial precision: Decimal for all NGN/USD amounts, NUMERIC(18,6) in PostgreSQL
Background tasks: FastAPI BackgroundTasks or Celery for forecasting -- never block the request
API versioning: all routes at /api/v1/ -- use include_router(prefix='/api/v1')
No print(): structlog.get_logger().info('event', key=value) everywhere

A.3  requirements.txt (complete dependency list)
# Web framework
fastapi==0.115.0
uvicorn[standard]==0.30.0
pydantic==2.8.0
pydantic-settings==2.4.0
 
# Database
sqlalchemy==2.0.35
alembic==1.13.2
asyncpg==0.29.0
 
# Auth
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
 
# AI / Forecasting
prophet==1.1.5
numpy==1.26.4
scipy==1.13.1
scikit-learn==1.5.1
pandas==2.2.2
 
# HTTP client
httpx==0.27.0
 
# Caching
redis==5.0.8
 
# Logging
structlog==24.4.0
 
# Testing
pytest==8.3.2
pytest-asyncio==0.23.8
pytest-cov==5.0.0
factory-boy==3.3.1
 
# Linting
ruff==0.6.3


A.4  FastAPI + Angular integration notes
The official FastAPI full-stack template uses React. For Angular, the integration approach is:
Backend serves the API only at http://localhost:8000/api/v1/
Angular frontend runs independently at http://localhost:4200/ (ng serve) or port 80 in prod
CORS: configure FastAPI to allow origins ['http://localhost:4200', 'https://your-prod-domain.com']
Authentication: Angular stores JWT in localStorage; AuthInterceptor adds Authorization header to every request
API contract: FastAPI's auto-generated OpenAPI spec at /docs is the single source of truth for Angular service interfaces
In Docker: frontend and backend are separate containers sharing a Docker network (see docker-compose.yml)

# backend/src/main.py -- CORS config for Angular dev
from fastapi.middleware.cors import CORSMiddleware
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:4200'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)



Appendix B -- Angular 17 coding standards



Angular 17 introduces standalone components, Signals, and inject() as first-class patterns. All FXWise components must follow these conventions. These are embedded in the Coder Agent.

B.1  Standalone component template
import { Component, ChangeDetectionStrategy, input, output, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
 
@Component({
  selector: 'app-metric-card',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './metric-card.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class MetricCardComponent {
  // Use inject() -- no constructor injection
  private readonly router = inject(Router);
 
  // Signal-based inputs (Angular 17+ API)
  title  = input.required<string>();
  value  = input.required<number>();
  trend  = input<'up' | 'down' | 'flat'>('flat');
  clicked = output<void>();
 
  // Computed signal
  formattedValue = computed(() =>
    new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' })
      .format(this.value())
  );
}


B.2  Service with signal-based state
import { Injectable, signal, inject } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { ApiService } from '../core/services/api.service';
import { FxExposure } from './models/fx-exposure.model';
 
@Injectable({ providedIn: 'root' })
export class FxService {
  private readonly api = inject(ApiService);
 
  // Private writable signal
  private readonly _exposure = signal<FxExposure | null>(null);
 
  // Public read-only signal exposed to components
  readonly exposure = this._exposure.asReadonly();
 
  loadExposure(): Observable<FxExposure> {
    return this.api.get<FxExposure>('/fx/exposure').pipe(
      tap(data => this._exposure.set(data))
    );
  }
}


B.3  Key rules
Standalone components only -- no NgModule declarations anywhere in FXWise
ChangeDetectionStrategy.OnPush on every component -- prevents wasted re-renders
Use signal input()/output() APIs (Angular 17+) not the legacy @Input()/@Output() decorators
Never use TypeScript 'any' -- create interfaces for every API response shape
HTTP calls only in services -- components subscribe to service signals
GlobalErrorInterceptor handles all HTTP errors -- components never catch HTTP errors
Lazy-load all feature routes -- no eager loading
TailwindCSS for all styling -- if a style cannot be expressed in Tailwind, add a utility class to styles.css
Use Angular's async pipe in templates rather than .subscribe() in component class


Appendix C -- All human checkpoints at a glance



Every action you need to take personally is listed here. Everything else is handled by Claude.

#
When
What you do
Time
H-01
Before starting
Install tools: Node, Python, Git, Docker, CLIs
30 min
H-02
Step 1.2
Create Anthropic Console + GitHub accounts
10 min
H-03
Step 1.3
Collect API keys: ANTHROPIC_API_KEY, PERPLEXITY_API_KEY
5 min
H-04
Step 1.4
Run: claude login  and  gh auth login
5 min
H-05
Step 2.1
Run: gh repo create fxwise --private --clone
5 min
H-06
Step 2.1
Add GitHub Secrets: ANTHROPIC_API_KEY, POSTGRES_PASSWORD, SECRET_KEY
5 min
H-07
Step 5.1
Paste full PRD text into .taskmaster/docs/prd.txt and save
10 min
H-08
Step 5.4
Review generated tasks, verify all modules covered, adjust priorities
15 min
H-09
Every task Step 2
Read active-plan.md -- type 'Plan approved' or 'Revise: <feedback>'
5 min each
H-10
Every task Step 4
Merge the PR on GitHub after Reviewer Agent approves
2 min each
H-11
Every task Step 5
Run: task-master set-status --id N --status done
1 min each
H-12
After task 2 (DB schema)
Review Alembic migration files -- confirm schema matches PRD entities
15 min
H-13
After task 9 (forecasting)
Check Prophet model output -- confirm forecast looks reasonable
20 min
H-14
After task 14 (first dashboard)
Visual review in browser -- confirm design matches PRD specs
15 min
H-15
After task 21 (final)
Full smoke test: login, enter sales, create order, view dashboard
30 min


TOTAL HUMAN TIME ESTIMATE
Total estimated human time for Stage A: 4-6 hours spread across the full build.
The majority of your time is in plan approval (H-09): 21 tasks x 5 min = ~105 min.
All other checkpoints together are under 2.5 hours.

Without this automation: 3-5 weeks of full-time development.


-- End of Setup Guide --
