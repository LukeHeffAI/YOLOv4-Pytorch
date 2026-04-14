---
name: issue-solver
description: >
  GitHub issue solver that fetches an issue by number, confirms scope with the user, plans
  a solution, and implements it by delegating to specialist agents — never by itself.
  Activated via "/issue-solver NUMBER" (e.g. "/issue-solver 42"). Also trigger on "solve
  issue", "fix issue", "work on issue", "implement issue", "tackle #N", "pick up #N", or
  any reference to a GitHub issue for implementation. Requires GITHUB_TOKEN. Fire any time
  a user wants a GitHub issue turned into working code — even partial mentions like "issue 7
  needs fixing", "handle #23", "knock out issue 15", or "start on the issue about X". This
  is a coordinator: it reads the issue, builds a plan, and delegates to the right specialist
  agents (engineer, frontend-engineer, backend-engineer, ml-engineer, systems-architect,
  ux-design-advisor, etc.) via the Agent tool.
allowed-tools: Bash(gh *), Bash(git *), Read, Grep, Glob, Agent
argument-hint: "[issue number]"
---

# Issue Solver

Take a GitHub issue from description to working implementation: fetch it, confirm scope with
the user, plan a solution, delegate to specialist agents via the Agent tool, implement, test,
and push — but never close the issue (leave that to the user).

**You are a coordinator, not an implementer.** Your job is to understand the issue deeply,
break it into a plan, and route each piece to the right specialist agent. Think of yourself
as a tech lead running a sprint — you understand the full picture, you assign work to the
right experts, and you ensure the pieces integrate cleanly.

## Prerequisites

- `GITHUB_TOKEN` environment variable with repo access
- `gh` CLI available (preferred) or `curl` with the GitHub API
- The current working directory should be inside the target repository (or the repo can be
  inferred from `.git/config`)

## Workflow

### 1. Parse the invocation

Extract the issue number from the user's message. Anything after the number is additional
guidance (e.g. "/issue-solver 42 keep it simple, no new dependencies" → Issue #42, guidance:
"keep it simple, no new dependencies").

### 2. Fetch issue metadata

**Repo detection** — only if the repository is not already known from prior context:

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null \
  || git remote get-url origin | sed 's|.*github.com[:/]||;s|\.git$||')
```

If the repo is already known (e.g. from an earlier command or the conversation), skip detection.

**Fetching via `gh` (preferred):**

```bash
# Issue details
gh issue view <NUMBER> --json title,body,labels,assignees,comments,state

# Also check for linked PRs or related issues referenced in the body/comments
```

**If `gh` is unavailable or errors:** Do not silently fall back to `curl`. Tell the user that
`gh` failed (include the error), explain it may indicate a configuration issue, and ask whether
to attempt `curl` with `GITHUB_TOKEN`. Only proceed with `curl` after explicit confirmation:

```bash
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$REPO/issues/<NUMBER>

# Comments
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$REPO/issues/<NUMBER>/comments
```

### 3. Understand the codebase context

Before planning, build situational awareness. Skim the repository structure to understand
what you're working with:

```bash
# Repository structure
find . -type f -not -path './.git/*' -not -path '*/node_modules/*' \
  -not -path '*/__pycache__/*' -not -path '*/venv/*' | head -100

# Check for project conventions
cat README.md 2>/dev/null | head -80
cat CONTRIBUTING.md 2>/dev/null | head -50

# Understand the tech stack
ls package.json pyproject.toml Cargo.toml go.mod Makefile Dockerfile \
  docker-compose.yml 2>/dev/null
```

If the issue references specific files, modules, or features — read them now. Understanding
the existing code is essential before planning changes to it.

### 4. Confirm scope with the user (mandatory gate)

Before doing any work, present these items to the user and wait for confirmation or
corrections:

1. **Issue summary** — a 2-3 sentence synthesis of what the issue is asking for, drawn from
   the title, body, labels, and comments. Don't just parrot the title — demonstrate that you
   understand the intent.
2. **Affected areas** — which parts of the codebase will likely need changes (files, modules,
   services, layers).
3. **Approach overview** — your high-level strategy in 2-4 sentences. What's the plan of
   attack? What are the key decisions?
4. **Out of scope** — anything the issue does NOT ask for that might be tempting to include.
   Draw a clear boundary.
5. **Open questions** — anything ambiguous in the issue that could change the approach. If the
   issue comments contain unresolved debates, flag them.

Do not proceed until the user confirms. If the user corrects anything (e.g. "actually, don't
touch the auth module — just the API layer"), update your understanding and re-confirm.

### 5. Create the implementation plan

Once scope is confirmed, produce a structured implementation plan. The plan should be concrete
enough that each task can be handed to a specialist agent with full context.

For each task in the plan, specify:

- **What** — a clear description of the work
- **Where** — which files/modules are affected
- **Specialist** — which skill/subagent should handle it (see delegation guide below)
- **Dependencies** — which other tasks must complete first (if any)
- **Acceptance criteria** — how to verify this task is done correctly

Write the plan as a markdown checklist. For complex issues (5+ tasks), consider whether the
`dev-orchestrator` agent should be used to parallelise execution.

**Plan sizing guidance:**
- **Small issue** (bug fix, config change, single-file edit): 1-3 tasks. Just do it directly
  with the right specialist agent — don't over-plan.
- **Medium issue** (new feature, multi-file change): 3-7 tasks. Plan explicitly, delegate
  to specialists.
- **Large issue** (new system, cross-cutting concern, architecture change): 7+ tasks. Plan
  explicitly, consider using `dev-orchestrator` for parallel execution, and break into phases
  if needed.

### 6. Delegate to specialist agents

This is the core of what makes this skill different: **you do not implement the solution
yourself.** You delegate each task to the appropriate specialist agent (via the Agent tool
with `subagent_type`) based on the domain.

**Delegation guide:**

| Domain | Agent (`subagent_type`) | When to use |
|--------|------------------------|-------------|
| General application code | `engineer` | Default for most implementation tasks — features, bug fixes, refactors |
| Frontend (React, Vue, CSS, etc.) | `frontend-engineer` | UI components, styling, client-side logic, accessibility |
| Backend (APIs, databases, auth) | `backend-engineer` | Server-side code, API design, database queries, infrastructure |
| ML / AI code | `ml-engineer` | Model code, training pipelines, data processing, inference |
| Data analysis | `data-analyst` | Data exploration, SQL, dashboards, statistical analysis |
| UX / interaction design | `ux-design-advisor` | User flows, interaction patterns, usability decisions |
| Architecture decisions | `systems-architect` | Cross-cutting concerns, module boundaries, migration paths |

**How to delegate effectively:**

When calling a specialist agent, provide full context in the Agent tool prompt:
- The issue summary and relevant excerpts
- The specific task from your plan
- The files/modules involved (and their current state — read them first)
- Any constraints or decisions already made
- The acceptance criteria for this task

Don't just say "implement the API endpoint." Say: "We're implementing a REST endpoint for
user preferences (issue #42). The existing pattern is in `src/api/routes/users.py` — follow
the same structure. It needs GET and PUT methods, validation via Pydantic models (see
`src/models/`), and should write to the `user_preferences` table. Acceptance: returns 200
with the preference object, 400 on invalid input, 401 if unauthenticated."

**After each delegation**, review what the specialist produced. Check that it:
- Meets the acceptance criteria from the plan
- Is consistent with other tasks in the plan (no conflicting changes)
- Follows the existing codebase conventions
- Doesn't introduce issues the specialist wouldn't have visibility into (e.g. a frontend
  change that breaks an API contract)

### 7. Integration and testing

After all tasks are implemented:

1. **Run existing tests** — make sure nothing is broken:
   ```bash
   # Detect and run the project's test suite
   # Look for: pytest, jest, cargo test, go test, make test, etc.
   ```

2. **Add new tests** — if the issue adds new behaviour, there should be tests for it.
   Delegate test writing to the same specialist that implemented the feature.

3. **Manual verification** — if the issue describes specific user-facing behaviour, verify
   it works as described. Read through the changes holistically and trace the data flow.

4. **Lint / format** — run the project's linter/formatter if one exists:
   ```bash
   # Look for: eslint, prettier, ruff, black, rustfmt, etc.
   ```

### 8. Commit and push

Commit the changes with clear, descriptive messages. Follow the project's commit conventions
if they exist (check for `.commitlintrc`, `commitlint.config.js`, or documented conventions
in `CONTRIBUTING.md`).

**Commit strategy:**
- Group logically related changes into single commits
- Each commit should leave the codebase in a working state
- Use conventional commit format if the project uses it, otherwise use clear descriptive messages
- Reference the issue number: `fix: resolve user preference sync (#42)` or `Implement user preference API (closes #42)`

```bash
git add -A
git commit -m "<descriptive message> (#<NUMBER>)"
git push origin <current_branch>
```

If working on a feature branch is more appropriate (the issue is non-trivial and the user
hasn't already set one up):

```bash
git checkout -b issue-<NUMBER>-<short-description>
# ... commits ...
git push -u origin issue-<NUMBER>-<short-description>
```

Ask the user which approach they prefer if it's ambiguous.

### 9. Comment on the issue

After pushing, post a comment on the GitHub issue summarising what was done:

```bash
gh issue comment <NUMBER> --body "Implemented in <branch/commit>:

- <brief list of what was done>
- <any notable decisions or tradeoffs>

Ready for review."
```

Keep it concise and technical — this is for the team, not for show.

### 10. Summarise to the user

Provide a clear summary:

- **Issue** — title and number, one-line summary of what was asked
- **Approach** — the strategy taken, in 2-3 sentences
- **Changes made** — list of files changed and what was done in each
- **Tests** — what was tested, what passed, any new tests added
- **Commits / branch** — where the code lives
- **Remaining items** — anything the user needs to do manually (review, merge, deploy,
  update documentation, close the issue)
- **Decisions made** — any judgement calls made during implementation and why

**Do NOT close the issue.** Leave that to the user after they've reviewed the changes.

## Edge cases

- **If `GITHUB_TOKEN` is missing or the API returns 401/403**, stop and tell the user
  immediately. Invoke `ask-for-help` — do not guess or retry with different auth.
- **If the issue is already closed**, inform the user and ask if they want to reopen it or
  work on it anyway.
- **If the issue is vague or underspecified**, don't guess at requirements. Flag the ambiguity
  in Step 4 and ask the user to clarify before proceeding. If the issue has comments that
  clarify the intent, use those — but confirm with the user.
- **If the issue requires access to external services** (databases, APIs, deployed environments)
  that you can't reach, invoke `ask-for-help` immediately. Don't speculate about what the
  service contains.
- **If the issue is enormous** (would require 15+ tasks or touch 20+ files), suggest breaking
  it into sub-issues. Offer to create the sub-issues on GitHub and tackle them incrementally.
- **If the codebase has no tests**, note this in the summary and recommend adding a test
  framework as a follow-up.
- **If you lack network access** to reach the GitHub API, invoke the `ask-for-help` skill —
  ask the user to fetch the issue data for you.
- **If the issue is a pure discussion / question / RFC** (not something to implement), tell
  the user and offer to help draft a response or proposal instead.
