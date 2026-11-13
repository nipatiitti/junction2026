# CLAUDE.md

The workflow for this repository lives in `AGENTS.md` and applies in full:

@AGENTS.md

## Claude Code specifics

How to carry out that workflow with Claude Code's tools:

- Issues and pull requests go through the GitHub tools.
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
