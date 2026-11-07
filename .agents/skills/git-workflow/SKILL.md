---
name: git-workflow
description: Safely manage Git branches, status, diffs, commits, pull requests, and merges for this repository. Use for Git operations, branch planning, PR review, or merge readiness.
---

# Git Workflow

## Repository rules
- Branch names use `<type>/<task-id>-<short-name>`, including documentation work.
- Never work directly on `main`. Start from the latest verified `origin/main`.
- Keep each branch/task bounded. Do not mix unrelated changes.
- Never discard, overwrite, reset, or stash user changes without explicit instruction.

## Before changes
1. Run `git status --short --branch`; stop if unexpected local changes exist.
2. Fetch remote refs and confirm the base commit.
3. Create/switch to the task branch.
4. Inspect relevant files before editing.

## Before commit/PR
1. Review `git diff --check`, `git diff --stat`, and the full diff.
2. Confirm only in-scope files changed; check secrets, generated files, lockfiles, and accidental artifacts.
3. Run task-appropriate tests or state precisely why they were not run.
4. Use a concise conventional commit message and document evidence honestly.

## Pull requests and merges
- PRs target `main` unless the task explicitly specifies otherwise.
- Describe scope, exclusions, tests/evidence, limitations, and linked task/issue.
- Review mergeability, CI, changed files, and branch freshness before merging.
- A PR being mergeable is not approval to merge. Require explicit Product Owner merge approval for code/runtime changes.
- Never force-push, rewrite shared history, delete branches, or merge on behalf of the Product Owner without explicit authorization.
- After merge, verify PR state and `main` commit; provide exact commands for local synchronization.
