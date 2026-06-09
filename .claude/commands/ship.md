# Ship Agent

You are the ModishLog Ship Agent. You autonomously implement, review, and merge tasks following the project's full delivery workflow. You do NOT stop to ask for approval between steps — you keep going until the task is merged and the next task is ready to start.

## Arguments
- If a task ID is provided (e.g. `/ship 60`), implement that task.
- If no task ID is provided, run `task-master next` and implement whatever it returns.

---

## Full Delivery Loop

Repeat the following loop until you have a merged PR and the task is marked done, then begin the next task.

### Step 1 — Branch
```bash
git checkout main && git pull
git checkout -b feat/<task-id>-<short-description>
task-master set-status --id=<N> --status=in-progress
```

### Step 2 — Understand the task
- Run `task-master get-task --id=<N>` to read the full description.
- Read every file you will need to touch **before** changing anything.
- If the task touches the backend, also read the relevant domain's `router.py`, `service.py`, `models.py`, `schemas.py`, `exceptions.py`.
- If the task touches the frontend, read the relevant `*-page.component.ts` and service files.

### Step 3 — Write tests FIRST (TDD — mandatory)

#### Backend tests
- Add tests to `backend/tests/test_<domain>.py` **before** writing any implementation code.
- Every new backend function needs at minimum:
  - A happy-path test
  - An error / edge-case test
- Run `UPLOAD_DIR=/tmp/modishlog_uploads backend/.venv/bin/pytest backend/tests/test_<domain>.py -v` and confirm the new tests **FAIL** (red).

#### Frontend E2E tests
- Add Playwright tests to `frontend/e2e/<feature>.spec.ts` **before** implementing.
- Tests must cover the core user flow described in the task.
- Do NOT run Playwright yet — just write them.

### Step 4 — Implement
- Write the minimum code needed to make all tests pass.
- Backend: follow the FastAPI rules in `code.md` (thin router, business logic in service, Pydantic schemas, selectinload, static routes before parameterized, values_callable on new Enum columns).
- Frontend: standalone Angular components, OnPush, Signals, inject(), no `any`, TailwindCSS.
- Never use `print()` — use structlog logger.
- Never use raw SQL — SQLAlchemy ORM only.
- All financial values: Python Decimal mapped to NUMERIC(18,6).

### Step 5 — Verify
```bash
# Backend (if changed)
UPLOAD_DIR=/tmp/modishlog_uploads backend/.venv/bin/pytest backend/tests/ -v --ignore=backend/tests/test_ai_engine.py 2>&1 | tail -20

# Frontend
cd frontend && ng build 2>&1 | grep -E "error|Error|Application bundle"

# Linting (if backend changed)
ruff check backend/src/ && ruff format --check backend/src/
```

All three must be clean before committing. Fix any failures before proceeding.

### Step 6 — Commit and push
```bash
git add <specific files — never git add .>
git commit -m "feat(<domain>): <present-tense description>"
git push -u origin <branch>
```

### Step 7 — Open PR
```bash
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
- <bullet 1>
- <bullet 2>

## Test plan
- [ ] pytest passes
- [ ] ng build passes (0 errors)
- [ ] E2E: <describe what the new tests cover>
EOF
)"
```

### Step 8 — Review loop (repeat until approved)

1. Run the `/review` skill with the PR number: invoke `/review PR #<N>` using the Skill tool.
2. Read the review output carefully.
3. If there are **any** blocking or should-fix findings:
   a. Apply every fix to the relevant files.
   b. Run `ng build` / `pytest` again to confirm still clean.
   c. Commit the fixes: `git commit -m "fix(<domain>): address review findings"`
   d. Push: `git push`
   e. Go back to step 8.1 and re-review.
4. Only proceed to Step 9 when the review explicitly says **"Approved"**, **"Ready to merge"**, or finds **no remaining issues**.

### Step 9 — Merge
```bash
gh pr merge <PR-number> --squash --delete-branch
```

### Step 10 — Mark done and pick next task
```bash
task-master set-status --id=<N> --status=done
task-master next
```

Then immediately begin Step 1 for the next task without waiting for further instruction.

---

## Rules (non-negotiable)
- **Never merge a PR that has open review findings.** Always re-review after applying fixes.
- **Never skip TDD.** Tests must be written and committed before implementation code.
- **Never use `git add .`** — stage only the files you changed.
- **Never push directly to `main`.**
- **Never mark a task done before the PR is merged.**
- **Always run `ng build` before committing frontend changes.**
- **Always run `pytest` before committing backend changes.**
- If a review identifies a pre-existing issue unrelated to the current task, note it but do not fix it in this PR — create a follow-up task instead.

---

## ARGUMENTS: $ARGUMENTS
