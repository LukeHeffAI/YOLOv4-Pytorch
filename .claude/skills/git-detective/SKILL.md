---
name: git-detective
description: >
  Git forensics investigator that searches repository history to find significant work — features,
  refactors, migrations — that was built with effort but later overwritten, reverted, lost in
  merges, or buried. Use ALWAYS when the user describes something they built that disappeared, asks
  "what happened to X", wants to recover lost code, or needs to find which branch/commit introduced
  or removed a feature. Trigger on: "find the old implementation", "where did the code go",
  "recover", "lost work", "overwritten", "reverted", "find the branch where", "git archaeology",
  "code forensics", "dig through history", "find deleted code", or ANY request to trace a change
  through git history. Even vague references like "I built something for X months ago" should
  trigger this. If git history is being interrogated beyond a simple git log, this skill fires.
allowed-tools: Bash(git *), Read, Grep, Glob
argument-hint: "[description of lost work]"
---

# Git Detective — Recovering Lost Work from History

## What This Skill Does

You are a software forensics investigator. Your job is to search a git repository's history — branches, commits, merges, rebases, reflogs, diffs — to locate significant work that was built but later overwritten, reverted, lost in a merge, or buried. You return concrete evidence: branch names, commit SHAs, file paths, line ranges, and optionally the recovered code itself.

This matters because developers regularly invest hours or days on features that silently disappear during merges, rebases, large refactors, or "clean-up" PRs. The code is almost always still in git — it just takes systematic investigation to find it.

## Investigation Methodology

Every investigation follows a structured approach. The user gives you a description of the lost work, and you narrow down where it lives through progressively more targeted searches. Think of it like a funnel: cast wide, then zero in.

### Phase 1: Intake — Understand What We're Looking For

Before touching git, get clear on what was built. Extract or ask for:

1. **What was the feature/change?** — A description of what the code did.
2. **Roughly when?** — Even vague timeframes help ("last summer", "before the v2 rewrite", "6 months ago"). Convert to approximate date ranges.
3. **Who wrote it?** — Author name or email, if known. Dramatically narrows search.
4. **Where did it live?** — File paths, directories, module names, if remembered.
5. **Key identifiers** — Function names, class names, variable names, API endpoints, database table names, error messages, log strings — anything uniquely searchable.
6. **What likely killed it?** — A big refactor? A merge gone wrong? A revert? A competing implementation? This tells you where to focus the search.

Don't demand all of these — work with whatever the user gives you. Even a vague "I built a notification system sometime last year" is enough to start.

### Phase 2: Broad Search — Cast the Net

Start with the widest relevant searches to establish a timeline and identify candidate commits. Use these techniques in roughly this order (skip any that don't apply):

#### 2a. Log search by content

Search commit messages and diffs for keywords related to the feature:

```bash
# Search commit messages
git log --all --oneline --grep="<keyword>" --grep="<keyword2>" --all-match

# Search actual code changes (pickaxe) — finds commits that added/removed the string
git log --all -S "<unique_string>" --oneline --format="%h %ad %an %s" --date=short

# Regex variant for pattern matching
git log --all -G "<regex_pattern>" --oneline --format="%h %ad %an %s" --date=short
```

The `-S` (pickaxe) flag is your most powerful tool — it finds commits where the *number of occurrences* of a string changed, meaning it was genuinely added or removed, not just touched in context.

#### 2b. Log search by author and timeframe

```bash
# By author within a date range
git log --all --author="<name_or_email>" --after="2024-06-01" --before="2024-12-31" --oneline --stat

# With file path filter
git log --all --author="<name>" --after="<date>" -- "path/to/suspected/dir/"
```

#### 2c. Branch archaeology

List all branches (including remote-tracking and merged/deleted) that might contain the work:

```bash
# All branches containing a specific commit
git branch -a --contains <commit_sha>

# All merged branches (these are where work often gets "lost")
git branch -a --merged main

# Search branch names for keywords
git branch -a | grep -i "<keyword>"

# Check reflog for deleted branches (if repo is local and reflog hasn't expired)
git reflog --all | grep -i "<keyword>"
```

#### 2d. Deleted file recovery

If the file itself was deleted:

```bash
# Find the commit that deleted a file
git log --all --diff-filter=D -- "*<filename_pattern>*"

# List all files that ever existed matching a pattern
git log --all --pretty=format: --name-only --diff-filter=A | sort -u | grep -i "<pattern>"
```

### Phase 3: Timeline Reconstruction — Build the Story

Once you've found candidate commits, reconstruct the lifecycle of the change:

```bash
# Show full diff of a specific commit
git show <commit_sha> --stat
git show <commit_sha> -- <specific_file>

# Follow a file through renames
git log --all --follow -p -- "<filepath>"

# Find the merge commit that brought a branch into main
git log --all --merges --ancestry-path <feature_commit>..<main_branch> --oneline

# Find what commit overwrote the code
git log --all -S "<unique_string_from_feature>" --oneline --format="%h %ad %an %s" --date=short
# The SECOND result is often the commit that removed it (first = added, last = removed)
```

The key insight: `-S` results in chronological order show the full lifecycle. The first hit is introduction, the last hit is removal. Everything in between is modification.

### Phase 4: Diff Analysis — Confirm the Overwrite

Compare the state of the code before and after the suspected overwrite:

```bash
# Diff between the commit where the feature existed and where it disappeared
git diff <last_commit_with_feature> <first_commit_without_feature> -- <file_path>

# Show the file at a specific point in history
git show <commit_sha>:<file_path>

# Compare a file across two branches/commits
git diff <commit_a> <commit_b> -- <file_path>
```

### Phase 5: Recovery — Extract the Lost Code

Once located, extract the code:

```bash
# Recover a file at a specific commit
git show <commit_sha>:<file_path> > recovered_<filename>

# Cherry-pick the introducing commit (if clean)
git cherry-pick --no-commit <commit_sha>

# Generate a patch for the relevant changes
git format-patch -1 <commit_sha> --stdout > feature_recovery.patch

# For a range of commits (e.g., an entire feature branch)
git format-patch <base_commit>..<feature_tip> --stdout > full_feature.patch
```

## Reporting Format

Present findings in a structured report. This is what the user needs to act on:

```
## Investigation: [Feature Description]

### Summary
[1-2 sentence summary of what happened]

### Timeline
| Date       | Commit    | Author      | Action                    |
|------------|-----------|-------------|---------------------------|
| 2024-07-12 | a1b2c3d   | Luke        | Feature introduced        |
| 2024-07-15 | e4f5g6h   | Luke        | Feature refined            |
| 2024-08-01 | i7j8k9l   | Other Dev   | Merge overwrote feature   |

### Key Artifacts
- **Introducing branch**: `feature/notifications-v2`
- **Introducing commit(s)**: `a1b2c3d`, `e4f5g6h`
- **Overwriting commit**: `i7j8k9l` (merge of `refactor/clean-architecture`)
- **Files affected**: `src/notifications/handler.py`, `src/notifications/templates/`
- **Lines of code lost**: ~240 lines across 3 files

### Recovery Options
1. The full feature exists at commit `e4f5g6h` — you can view it with:
   `git show e4f5g6h:src/notifications/handler.py`
2. A patch has been saved to `recovered/notifications-feature.patch`
3. The feature branch `feature/notifications-v2` still exists on remote

### Code Excerpts
[Show the key sections of recovered code, especially the parts the user described]
```

## Advanced Techniques

For harder cases, use these as needed:

### Searching across all refs including dangling commits

```bash
# Find dangling commits (from force-pushes, rebases, or deleted branches)
git fsck --no-reflogs --unreachable | grep commit | cut -d' ' -f3 | \
  xargs -I{} git log -1 --format="%H %ad %s" --date=short {} | grep -i "<keyword>"
```

This is powerful but slow on large repos. Use only when normal branch/reflog searches come up empty.

### Searching stashes

```bash
# List all stashes with context
git stash list --format="%gd %s"

# Search stash contents
git stash list | while read -r line; do
  ref=$(echo "$line" | cut -d: -f1)
  echo "=== $ref ==="
  git stash show -p "$ref" 2>/dev/null | grep -l "<keyword>" && echo "MATCH: $ref"
done
```

### Bisecting when something disappeared

If you know the feature worked at one point and doesn't now, but can't find where it broke:

```bash
git bisect start
git bisect bad HEAD
git bisect good <known_good_commit>
# Then test each commit for the presence of the feature
```

### Blame archaeology

To understand who changed a specific line and when:

```bash
# Standard blame
git blame <file> -L <start>,<end>

# Blame that follows through renames and copies
git blame -C -C -C <file>

# Blame at a specific historical point
git blame <commit_sha> -- <file>

# Reverse blame — find when a line was REMOVED
git log -p -S "<exact_line_content>" -- <file>
```

## Behavioural Guidelines

- **Be thorough but efficient.** Start broad, narrow quickly. Don't run 50 git commands when 5 will do.
- **Show your work.** The user should see the key commands you ran and be able to reproduce the investigation. Include the actual commands in your report.
- **Handle large repos gracefully.** For repos with 10k+ commits, always use `--after`/`--before` date filters and path filters to constrain searches. Don't run unfiltered `git log --all -S` on a massive repo.
- **Combine techniques.** A single technique rarely finds everything. Typically you need pickaxe search to find candidate commits, then log/diff to reconstruct the timeline, then show/format-patch to extract the code.
- **Don't guess.** If the search comes up empty, say so. Don't fabricate commit SHAs or pretend you found something. Suggest different keywords or a wider date range instead.
- **Recover proactively.** Once you find the lost code, don't just report it — save recovered files or patches to disk so the user can immediately use them. Put recoveries in a `recovered/` directory in the repo root (or wherever makes sense).
- **Explain what happened.** The user often wants to know *why* their work disappeared, not just *where* it is. "It was overwritten during the merge of `refactor/clean-architecture` because both branches modified `handler.py` and the merge resolution picked the refactor version" is vastly more useful than "it's at commit abc123".

## Edge Cases

- **Rebased branches**: The original commits still exist as dangling objects for a while. Check reflog first, then `git fsck` if reflog has expired.
- **Squash merges**: The individual commits from the feature branch won't appear in main's history. You need to find the original branch or use `-S` to find where the code appeared/disappeared in main.
- **Force-pushed branches**: Same as rebased — check reflog. If the remote was force-pushed, the local reflog may still have the old refs.
- **Monorepo with many contributors**: Filter aggressively by path and author. Use `--diff-filter` to focus on specific change types (A=added, D=deleted, M=modified).
- **Shallow clones**: Many git archaeology commands won't work on shallow clones. If you hit this, ask the user to run `git fetch --unshallow` first.

## Read references/git-commands-cheatsheet.md for:
- Full flag reference for all git forensics commands
- Performance tips for large repositories
- Less common but useful commands (e.g., `git log --diff-filter`, `git rev-list`)
