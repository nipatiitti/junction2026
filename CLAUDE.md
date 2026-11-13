# CLAUDE.md

The workflow for this repository lives in `AGENTS.md` and applies in full:

@AGENTS.md

## Claude Code specifics

How to carry out that workflow with Claude Code's tools:

- Testing is not allowed: do not write, change or run tests (no `pytest`,
  `node --test` or `pnpm test`), even where Claude Code's defaults would.

- One online run at a time (see `AGENTS.md`): run `dispatch.py`, `pnpm dispatch`
  or the bench in the foreground, or with `run_in_background` only when no other
  run is going, and wait for its result before you start the next one.
- Pull and rebase from main often (see `AGENTS.md`): run
  `git pull --rebase origin main` before you start, before each push and when
  main has moved. On a branch you have already pushed, use
  `git pull --no-rebase origin main` instead, so no force-push is needed.

- Issues and pull requests go through the GitHub tools.
- Mark the issue as started with `issue_write`, `method: "update"` and the new
  `title` (`In progress: <original title>`), before you create the branch.
- Open the PR with `create_pull_request` and `draft: true`. When the feature
  and its docs are done, move it to open with `update_pull_request` and
  `draft: false`, then check with `pull_request_read` that it is no longer a
  draft. This replaces Claude Code's default of opening PRs ready for review.
- After opening a PR, subscribe to its activity, so conflicts, CI failures and
  review comments reach you as events while the PR is open.
- Before you push to a branch that already has a PR, check that PR's state. A
  merged or closed PR does not pick up later pushes, so those commits would sit
  on the branch with nobody reviewing them. If it is merged or closed, merge the
  latest default branch into yours and open a new PR for the commits that are
  not in the default branch yet.

## Progress updates

Before you start, say in a line what you're about to do; brief updates while
you work help the user follow along. Close with a short recap that stands on
its own (what you found, what you did, and what's next), so a reader who only
sees the last message has the full picture.

Source: Anthropic's prompting guide,
https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2
