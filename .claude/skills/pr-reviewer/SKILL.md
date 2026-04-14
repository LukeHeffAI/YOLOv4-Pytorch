---
name: pr-reviewer
description: >
  GitHub pull request reviewer that fetches a PR by number, confirms the details with the user,
  then reviews, resolves conflicts, and pushes improvements. Activated via "/pr-reviewer NUMBER"
  (e.g. "/pr-reviewer 16"). Also trigger when the user says "review PR", "check pull request",
  "look at PR #N", or any variation referencing a GitHub PR number for review. Requires GITHUB_TOKEN
  in the environment. This skill should fire any time a PR review workflow is needed — even partial
  mentions like "PR 42 needs a look" or "can you review #12".
allowed-tools: Bash(gh *), Bash(git *), Read, Grep, Glob, Agent
argument-hint: "[PR number] [optional focus area]"
---

# PR Reviewer

Review a GitHub pull request: fetch it, confirm details with the user, assess changes and comments,
resolve conflicts, make improvements, and push — but never merge.

## Prerequisites

- `GITHUB_TOKEN` environment variable with repo access
- `gh` CLI available (preferred) or `curl` with the GitHub API
- The current working directory should be inside the target repository (or the repo can be inferred from `.git/config`)

## Workflow

### 1. Parse the invocation

Extract the PR number from the user's message. Anything after the number is additional guidance
for the review (e.g. "/pr-reviewer 16 focus on error handling" → PR #16, guidance: "focus on
error handling").

### 2. Fetch PR metadata

**Repo detection** — only if the repository is not already known from prior context:

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null \
  || git remote get-url origin | sed 's|.*github.com[:/]||;s|\.git$||')
```

If the repo is already known (e.g. from an earlier command or the conversation), skip detection.

**Fetching via `gh` (preferred):**

```bash
gh pr view <NUMBER> --json title,body,headRefName,baseRefName,state,mergeable,comments,reviews,files
gh pr diff <NUMBER>
```

**If `gh` is unavailable or errors:** Do not silently fall back to `curl`. Instead, tell the
user that `gh` failed (include the error), explain that it may indicate a configuration issue
worth fixing (e.g. missing install, expired auth), and ask whether they'd like you to attempt
`curl` with `GITHUB_TOKEN` as a workaround. Only proceed with `curl` after explicit confirmation:

```bash
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$REPO/pulls/<NUMBER>
```

### 3. Confirm details with the user (mandatory gate)

Before doing any work, present these three items to the user via the interview/question tool
and wait for confirmation or corrections:

1. **Head branch** — the branch being merged in
2. **Base branch** — the branch being merged into
3. **Core changes summary** — a 2-3 sentence summary of what the PR does, synthesised from the title, body, and diff

Do not proceed until all three are confirmed. If the user corrects any detail (e.g. "that's the
wrong base branch, it should be `main`"), update your understanding and re-confirm.

### 4. Checkout and sync

```bash
git fetch origin
git checkout <head_branch>
git pull origin <head_branch>
```

### 5. Resolve merge conflicts

Check if there are conflicts with the base branch:

```bash
git merge origin/<base_branch> --no-commit --no-ff
```

If conflicts arise:
- List conflicted files.
- Resolve them intelligently based on the intent of both branches. Prefer the head branch's
  intent where the PR's changes are deliberate; prefer base where head has drifted from upstream
  updates (e.g. dependency lockfiles, formatting).
- Stage resolved files and commit with a clear message: `resolve merge conflicts with <base_branch>`.
- If a conflict is ambiguous, ask the user before resolving.

If no conflicts, abort the merge (`git merge --abort`) and continue — there's nothing to fix.

### 6. Review the changes

Carefully read every changed file in the diff. For each file, assess:

- **Correctness** — logic bugs, off-by-one errors, race conditions, null safety
- **Design** — naming, structure, separation of concerns, DRY, appropriate abstraction level
- **Tests** — are new code paths tested? Are existing tests updated if behaviour changed?
- **Security** — injection, auth, secrets in code, unsafe deserialization
- **Performance** — unnecessary allocations, N+1 queries, blocking calls in async contexts
- **Documentation** — do public APIs have docstrings? Are comments accurate post-change?

Also read every existing comment and review on the PR. Evaluate comments on their technical
merit, not on who wrote them. If a comment raises a valid concern that isn't addressed in the
code, treat it as an action item.

**Track comments for later replies.** As you review, build a mental ledger of every unresolved
comment and review comment (both top-level PR comments and inline review comments). For each,
note the comment ID, author, what it requests, and what action you plan to take (fix, disagree,
ask user, etc.). You will reply to all of these after pushing your changes (see Step 9).

### 7. Delegate to specialist agents when appropriate

If the PR touches domains covered by specialist agents, spawn them via the Agent tool for a
deeper assessment. For example:
- ML model code → spawn `ml-engineer` agent
- Frontend components → spawn `frontend-engineer` or `ux-design-advisor` agent
- Backend / API / database code → spawn `backend-engineer` agent
- Data analysis or query logic → spawn `data-analyst` agent
- General application code → spawn `engineer` agent
- Infrastructure / deployment → spawn the relevant agent if available

Incorporate their findings into the review.

### 8. Make changes

For every issue found (from your review, from PR comments, or from specialist skill/subagent feedback):

- If it's a clear improvement and low-risk, **fix it directly** in the code. Commit each
  logical fix separately with a descriptive message.
- If it's high-risk, ambiguous, or a design-level decision, **ask the user** before changing.

Group commits logically. Don't create one mega-commit.

### 9. Push changes

Push the changes:

```bash
git push origin <head_branch>
```

### 10. Respond to PR comments

After pushing, reply to **every** PR comment and review comment that you addressed (or
considered). This closes the feedback loop for the original reviewers.

**Fetching comment IDs** — if you didn't capture them during review, fetch them now:

```bash
# Top-level issue comments
gh api repos/$REPO/issues/<NUMBER>/comments --jq '.[] | {id, user: .user.login, body: .body}'

# Review comments (inline on diff)
gh api repos/$REPO/pulls/<NUMBER>/comments --jq '.[] | {id, user: .user.login, path, body}'
```

**Replying to each comment:**

For **top-level issue comments**, reply in the PR conversation:

```bash
gh pr comment <NUMBER> --body "Re: @<author>'s comment about <topic> — <your response>"
```

Group multiple related top-level comments into a single reply if they're closely related, but
don't pack everything into one wall of text. Use a separate reply for each distinct topic thread.

For **inline review comments**, reply directly to the review comment so the response appears
in the correct file/line context:

```bash
gh api repos/$REPO/pulls/<NUMBER>/comments/<COMMENT_ID>/replies \
  -X POST -f body="<your response>"
```

**What to include in each reply:**

- If you **fixed** the issue: briefly say what you did and reference the commit if helpful
  (e.g. "Fixed in `abc1234` — switched to a parameterised query as suggested.").
- If you **partially addressed** it: explain what was done and what remains.
- If you **intentionally did not change** something: explain why (e.g. "Looked into this —
  the current approach is intentional because X. Happy to discuss further.").
- If you **deferred to the user**: say so (e.g. "Flagged this for @<pr-author> to decide —
  it's a design-level choice.").

Keep replies concise and technical. Don't be sycophantic ("Great catch!") — just address the
substance.

**If `gh` is unavailable for replies**, use the GitHub API directly:

```bash
# Reply to an issue comment (by posting a new issue comment referencing it)
curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"body": "<your response>"}' \
  https://api.github.com/repos/$REPO/issues/<NUMBER>/comments

# Reply to a review comment
curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"body": "<your response>"}' \
  https://api.github.com/repos/$REPO/pulls/<NUMBER>/comments/<COMMENT_ID>/replies
```

### 11. Summarise

Then provide a summary to the user:

- **What was reviewed** — files and areas examined
- **Issues found** — list each issue, its severity, and what was done (fixed / flagged)
- **Conflicts resolved** — if any, what the resolution strategy was
- **Commits pushed** — list of new commits with their messages
- **Comments responded to** — count and brief summary of replies posted
- **Remaining items** — anything the user still needs to decide or do manually
- **Recommendation** — whether the PR looks ready to merge, or what remains

**Do NOT merge the PR.** Leave that decision to the user.

## Edge cases

- If `GITHUB_TOKEN` is missing or the API returns 401/403, stop and tell the user immediately
  (do not guess or retry with different auth).
- If the PR is already merged or closed, inform the user and stop.
- If the diff is enormous (>5000 lines), warn the user and ask whether to focus on specific
  files/directories or proceed with the full review.
- If you lack network access to reach the GitHub API, invoke the `ask-for-help` skill —
  ask the user to fetch the data for you.
