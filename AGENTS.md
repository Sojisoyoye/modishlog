# ModishLog -- Agent Roster

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
