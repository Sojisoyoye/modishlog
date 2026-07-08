# ModishLog — Risk Assessment Session Bootstrap

Paste this entire prompt at the start of a new Claude session to run the full
three-phase risk assessment cycle. Each phase builds on the previous one.
Run them in order — do not skip ahead.

---

## HOW TO USE THIS

1. Start a new Claude session in the modishlog project directory
2. Paste Phase 1 below. Wait for the full risk matrix output before continuing.
3. Paste Phase 2 with the Phase 1 findings attached. Wait for implementation.
4. Paste Phase 3 to verify everything was fixed correctly.

---

## PHASE 1 — RISK ASSESSMENT (paste this first)

```
I need you to perform a holistic risk assessment of the ModishLog codebase.
Read the full prompt at:

  .claude/prompts/risk-assessment-holistic.md

Then do the following in order:

1. Read these files to ground the assessment in real code:
   - backend/src/core/config.py
   - backend/src/core/middleware.py
   - backend/src/core/rate_limit.py
   - backend/src/auth/router.py
   - backend/src/auth/service.py
   - backend/src/auth/models.py
   - backend/src/ai_engine/service.py
   - backend/src/pricing/service.py
   - backend/src/fx/service.py
   - backend/src/cashflow/service.py
   - backend/src/settings/models.py
   - backend/src/core/logging.py
   - CLAUDE.md
   - README.md

2. Produce a risk matrix with every finding from the assessment framework.
   Format each finding as:

   RISK-[N] | [Dimension] | [Severity] | [Likelihood]
   Description: one sentence
   File/Location: exact file and line if applicable
   Impact: who is affected and how
   Interconnects with: other risk IDs that compound this one
   NDPR/CBN impact: regulatory category if applicable

3. End with a prioritised action list:
   - CRITICAL findings (fix before any new feature work)
   - HIGH findings (fix within current sprint)
   - MEDIUM findings (schedule for next sprint)
   - LOW findings (backlog)

Do not suggest fixes yet — assessment only. Save the full output because
Phase 2 will use it.
```

---

## PHASE 2 — RISK MITIGATION (paste this after Phase 1 completes)

```
Now implement the mitigations for the risk findings from Phase 1.
Read the full prompt at:

  .claude/prompts/risk-mitigation-integrated.md

Work through findings in this order:
  1. All CRITICAL findings first
  2. All HIGH findings second
  3. MEDIUM and LOW only if time/context permits

For each finding you are fixing:
  a. State which RISK-[N] ID you are addressing
  b. Name the exact file(s) you will change
  c. Implement the fix following the patterns in risk-mitigation-integrated.md
  d. Write the test(s) specified for that mitigation BEFORE the implementation
     (TDD — tests must fail first, then pass after implementation)
  e. Run: UPLOAD_DIR=/tmp/modishlog_uploads backend/.venv/bin/pytest backend/tests/ -v
     and confirm tests pass before moving to the next finding

After all fixes are implemented:
  - Run: cd frontend && ng build
  - Confirm: 0 compile errors
  - Stage only the changed files (never git add .)
  - Create one commit per dimension (security commit, ethical commit, reliability commit)

Do not merge yet — Phase 3 verifies the fixes first.
```

---

## PHASE 3 — VERIFICATION (paste this after Phase 2 completes)

```
Now verify that all mitigations from Phase 2 were correctly implemented.
Read the full prompt at:

  .claude/prompts/risk-verification-comprehensive.md

Work through the verification matrix section by section:

  1. Security Verification — run each grep/curl/pytest check listed
  2. Ethical Verification — run each schema check and test
  3. Reliability Verification — run each timeout/fallback/pool check
  4. Integration Verification — run the cross-dimensional scenario tests

For each item in the checklist:
  - Run the specified command or inspection
  - Report: [CHECK ID] PASS | FAIL | NOT IMPLEMENTED
  - For FAIL: state the file and line, and what needs to change

After the checklist is complete:
  - Any FAIL goes back to Phase 2 for that specific finding only
  - Any NOT IMPLEMENTED that was in Phase 1's CRITICAL or HIGH list
    must be implemented before the session ends

When all CRITICAL and HIGH items are PASS:
  - Open one PR per dimension:
      feat(security): address security risk findings
      feat(reliability): address reliability risk findings
      feat(ethical): address ethical risk findings
  - Run /review on each PR before merging
  - Merge in order: security → reliability → ethical
    (each builds on the previous layer being stable)

Final output: a one-paragraph session summary stating:
  - How many risks were found (by severity)
  - How many were fixed in this session
  - What remains open and why
  - Save this summary to .claude/prompts/risk-session-log.md
    appended with today's date
```

---

## QUICK REFERENCE — what each prompt file contains

| File | Purpose | When to use |
|---|---|---|
| `risk-assessment-holistic.md` | Find all risks — security, ethical, reliability | Phase 1, quarterly audits |
| `risk-mitigation-integrated.md` | Implement fixes with exact file/code guidance | Phase 2, after assessment |
| `risk-verification-comprehensive.md` | 50+ checklist to prove fixes work | Phase 3, after mitigation |
| `risk-pre-pr-check.md` | Lightweight diff review before any PR | Before every PR |
| `risk-checks.yml` | CI automation — runs on every PR automatically | Automated, no manual step |
| `risk-session-bootstrap.md` | This file — entry point for a full assessment session | Start of a new session |

## MAINTENANCE

- Re-run this full cycle every quarter, or after:
  - A new domain module is added
  - A new external API integration is added
  - A dependency major version upgrade
  - Any production security incident
- After each cycle, append a dated summary to `risk-session-log.md`
- If a new risk pattern is found that the prompts don't cover, add it to
  `risk-assessment-holistic.md` and the corresponding check to `risk-checks.yml`
