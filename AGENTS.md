## Project Configuration

- **Language**: TypeScript
- **Package Manager**: pnpm
- **Add-ons**: experimental, ai-tools, drizzle, sveltekit-adapter, tailwindcss, playwright

---

# Agent workflow

Rules for every coding agent working in this repository. They are stack-agnostic:
the only stack-specific part is the [Commands](#commands) table.

The loop: **issue → branch → build → focused tests → PR → keep it green → merged.**
Optimise for speed. Small issues, small PRs, fast tests.

## 1. Start from an issue

- All work starts from a GitHub issue the user hands you. No issue, no code:
  if asked for a feature without one, create the issue first, then work from it.
- One issue = one feature, **including its documentation and its tests**. All
  three ship in the same PR.
- If the issue is unclear, do not stop to ask. Pick the most sensible
  interpretation, build it, and list your assumptions in the PR.
- If the issue is too big for one reviewable PR, build the smallest useful slice
  and file the rest as new issues.

## 2. Work in a branch or worktree

- Never commit to the default branch. Every issue gets its own branch, ideally
  in its own worktree so several agents can work in parallel:

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

- Build what the issue asks for and nothing else.
- Trivial fixes (a typo, a one-liner) in files you are already editing may go in
  the same PR.
- Everything else you notice — bugs, refactors, missing features, follow-ups —
  becomes a **new GitHub issue**. Do not fix it and do not start on it.
- Check for an existing issue before creating one. A new issue contains:
  - **Feature** – what to build and why, with acceptance criteria.
  - **Docs** – what documentation must be added or changed.
  - **Tests** – what behaviour the tests must cover.

## 4. Testing: light and fast

Tests exist to keep development fast, never to slow it down.

- Test the feature's behaviour: the main path plus the edge cases that matter.
  Do not chase coverage or test trivial code.
- Tests must be fast and isolated: no network, no real external services, no
  sleeps, no dependence on other tests or on run order. A feature's tests
  should finish in seconds.
- Keep tests next to, or named after, the feature they cover so they can be run
  on their own by path or by name.
- While developing and before opening the PR, run **only the tests for the code
  you touched**. The full suite is CI's job, not yours.
- The project must always have a way to run a subset of the tests. Keep it in
  the Commands table.
- Never skip, disable or delete a test to get a green run. Fix the code or fix
  the test.

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
- Description: **at most 500 characters of text.** What changed, any
  assumptions you made, and `Closes #<issue>`. Screenshots do not count
  towards the limit.
- Screenshots: add them when the change is visible (UI, CLI output, charts)
  and you are able to capture them. Skip them otherwise.
- One issue per PR. No unrelated changes.

## 7. Keep the PR mergeable

The PR is yours until it is merged or closed. Do not hand problems back to the
user:

- Merge conflicts: merge or rebase onto the latest default branch, resolve,
  re-run the focused tests, push.
- Failing CI: read the failure, fix the cause, push. Repeat until green.
- Review comments: address them and push, or reply briefly why not.
- Keep watching until the PR is merged or closed. Never merge it yourself —
  merging is the user's decision.

## Commands

Stack-specific. The first PR that introduces or changes tooling must fill this
in and keep it current. Every row must be a single copy-pasteable command.

| Task                     | Command |
| ------------------------ | ------- |
| Install dependencies     | _TBD_   |
| Run the app              | _TBD_   |
| Run one test file / dir  | _TBD_   |
| Run tests by name        | _TBD_   |
| Run the full test suite  | _TBD_   |
| Lint / format            | _TBD_   |

## Definition of done

- [ ] Feature works as the issue describes
- [ ] Focused tests added and passing
- [ ] Documentation updated
- [ ] Follow-up work filed as new issues
- [ ] PR open, ready for review, description ≤ 500 characters, `Closes #<issue>`
- [ ] No conflicts, CI green
