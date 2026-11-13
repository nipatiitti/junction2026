## Project Configuration

- **Language**: Python 3.15 for the dispatch system (`dispatch.py`), run with uv; TypeScript for code in `src/`
- **Package Manager**: pnpm
- **Runtime**: Node 22.18+, running `.ts` files directly (no build step)
- **Tooling**: Biome (lint and format), `tsc` (type check only), `node --test`

## The challenge

We are building a dispatch system for Spread, Bahn's Junction 2026 challenge: it quotes
car dealers and pays freelance drivers to move the cars, for one simulated week.

- The system is `dispatch.py`, in Python, run with uv. Before you change it, read
  `docs/spread/HANDBOOK.md`. `RULES.md` and `API.md` next to it are the full references.
  `README.md` has the setup, the dates and the baseline to beat.
- Practice weeks are free and repeatable: the same seed and level give the same week.
  Compare two versions of the system on the same seeds.
- Ask for approval before you play a ranking run (`--board`) or a final (`--final`). Each
  ranking world can be played once, and its score stays on the public rankings.

---

# Agent workflow

Rules for every coding agent working in this repository. They are stack-agnostic:
the only stack-specific part is the [Commands](#commands) table.

The loop: **issue → branch → build → focused tests → PR → keep it green → merged.**
Optimise for speed. Small issues, small PRs, fast tests.

## 1. Start from an issue

- All work starts from a GitHub issue the user hands you, so every change is
  tracked and reviewable. If asked for a feature without one, create the issue
  first, then work from it.
- One issue = one feature, **including its documentation and its tests**. All
  three ship in the same PR.
- If the issue is unclear, carry on rather than stopping to ask: waiting stalls
  the work, and the user can correct the result in review. Pick the most
  sensible interpretation, build it, and list your assumptions in the PR.
- If the issue is too big for one reviewable PR, build the smallest useful slice
  and file the rest as new issues.

## 2. Work in a branch or worktree

- Commit on a branch, not on the default branch. The default branch changes only
  through PRs the user approves, and separate branches let several agents work
  in parallel. The one exception is the first commit of an empty repository,
  with the user's approval. Every issue gets its own branch, ideally in its own
  worktree:

  ```bash
  git fetch origin
  git worktree add ../<repo>-<issue> -b <type>/<issue>-<short-slug> origin/<default-branch>
  ```

- Branch name: `<type>/<issue>-<short-slug>`, e.g. `feat/12-login-form`
  (`feat`, `fix`, `docs`, `chore`). If your environment assigns you a branch
  name, use that one instead.
- Commits: small, imperative subject line, reference the issue (`Add login form (#12)`).
- Remove the worktree once the PR is merged or closed.

## 3. Stay in scope

- The user owns this codebase. Build what the issue asks for and leave the rest
  of the code as it is, so PRs stay small and quick to review.
- Trivial fixes (a typo, a one-liner) in files you are already editing may go in
  the same PR.
- Everything else you notice — bugs, refactors, missing features, follow-ups —
  becomes a **new GitHub issue** instead of a change. The user decides whether
  and when it is built, so leave it for the agent they assign.
- Check for an existing issue before creating one. A new issue contains:
  - **Feature** – what to build and why, with acceptance criteria.
  - **Docs** – what documentation must be added or changed.
  - **Tests** – what behaviour the tests must cover.
- Write the issue for a reader who has not seen your work: key point first,
  plain words, full sentences, and only names that exist in the code or the UI.

## 4. Testing: light and fast

Tests exist to keep development fast. A slow suite defeats that.

- Test the feature's behaviour: the main path plus the edge cases that matter.
  Skip coverage targets and tests of trivial code: they cost time without
  catching bugs.
- Tests must be fast and isolated: no network, no real external services, no
  sleeps, no dependence on other tests or on run order. That keeps them quick
  and lets any one of them run alone. A feature's tests should finish in seconds.
- Keep tests next to, or named after, the feature they cover so they can be run
  on their own by path or by name.
- While developing and before opening the PR, run **only the tests for the code
  you touched**. The full suite is CI's job, not yours.
- The project must always have a way to run a subset of the tests. Keep it in
  the Commands table.
- A green run has to mean the feature works. Fix the code or fix the test
  rather than skipping, disabling or deleting a test to get there. Removing a
  test is fine when the issue removes the behaviour it covers.

## 5. Documentation

- Document the feature in the same PR: update `README.md` or the relevant page
  under `docs/`. Say what it does and how to use it — keep it short.
- If you change how the project is run, built or tested, update the Commands
  table below in the same PR.

## 6. Pull request

Open the PR as soon as the feature, its docs and its focused tests are done.
It must be **ready for review** (not a draft) and ready for the user to approve
without further questions.

- Title: short, imperative, under 70 characters.
- Description: **at most 500 characters of text**, written for a reader who has
  not seen your work: key point first, plain words, full sentences, and only
  names that exist in the code or the UI. Cover what changed — every behaviour
  change, including small ones — your assumptions, and `Closes #<issue>`.
  Screenshots are outside the limit.
- Screenshots: add them when the change is visible (UI, CLI output, charts)
  and you are able to capture them. Skip them otherwise.
- One issue per PR, with nothing unrelated in it, so review stays quick.

## 7. Keep the PR mergeable

The PR is yours until it is merged or closed. Fix what comes up yourself rather
than handing it back, so the user's only job is to approve:

- Merge conflicts: merge the latest default branch into yours (a merge needs no
  force-push), resolve, re-run the focused tests, push.
- Failing CI: read the failure, fix the cause, push. Repeat until green.
- Review comments: address them and push, or reply briefly why not.
- Keep watching until the PR is merged or closed. Ask for approval before
  merging: when the change lands is the user's decision.
- When the PR is merged, check that its issue is closed. `Closes #<issue>` in
  the description closes it on merge; if it is still open, close it as
  completed, so that nobody picks up work that is already done. If the PR was
  closed without merging, close its issue as not planned, unless a new PR
  replaces it.

## 8. Keep going, and know when to ask

Finish the issue in one go. Ending with a list of what is left, or an offer to
continue, leaves the user with a half-built feature.

- Ordinary obstacles — errors, timeouts, failing tools, empty results — are
  yours to solve. Find the cause, then retry, fix the request or take another
  route.
- Deliberate blockers — withheld access, a file marked as protected, a safety
  guardrail — were put there on purpose. Leave them in place, say what you
  found, and look for another way to finish.

These routine steps need no approval: create a branch or worktree, commit, push
to your own branch, open a PR, create follow-up issues, reply on your own PR,
resolve merge conflicts, fix CI, close the issue of your own merged or closed
PR.

Ask for approval before these, because they are hard to undo or change what
other people see: merging a PR, pushing to the default branch, force-pushing,
deleting a branch, closing or editing any other issue you did not create.

## Commands

Stack-specific. The first PR that introduces or changes tooling must fill this
in and keep it current. Every row must be a single copy-pasteable command.

| Task                        | Command                                                       |
| --------------------------- | ------------------------------------------------------------- |
| Install dependencies        | `pnpm install`                                                |
| Run one test file / dir     | `node --test src/path/to/file.test.ts`                        |
| Run tests by name           | `node --test --test-name-pattern="<name>" "src/**/*.test.ts"` |
| Run the full test suite     | `pnpm test`                                                   |
| Lint / format               | `pnpm format`                                                 |
| Lint only (no writes)       | `pnpm lint`                                                   |
| Type check                  | `pnpm check`                                                  |
| Install Python dependencies | `uv sync`                                                     |
| Play a Spread practice week | `uv run dispatch.py --level 8 --seed spread-1`                |
| Write an ended week to CSV  | `uv run spread-reveal-csv <world id>`                         |
| Run one Python test file    | `uv run pytest tests/test_dispatch.py`                        |
| Run Python tests by name    | `uv run pytest -k "<name>"`                                   |
| Run all Python tests        | `uv run pytest`                                               |
| Lint / format Python        | `uv run ruff check --fix . && uv run ruff format .`           |

## Definition of done

- [ ] Feature works as the issue describes
- [ ] Focused tests added and passing
- [ ] Documentation updated
- [ ] Follow-up work filed as new issues
- [ ] PR open, ready for review, description ≤ 500 characters, `Closes #<issue>`
- [ ] No conflicts, CI green
