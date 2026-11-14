## Project Configuration

- **Language**: Python 3.15 for the dispatch system (`dispatch.py`), run with uv; TypeScript for code in `src/` (the dispatch system `src/dispatch.ts`, on the vendored kit in `vendor/spread-typescript/`)
- **Package Manager**: pnpm
- **Runtime**: Node 22.18+, running `.ts` files directly (no build step)
- **Tooling**: Biome (lint and format), `tsc` (type check only)

## The challenge

We are building a dispatch system for Spread, Bahn's Junction 2026 challenge: it quotes
car dealers and pays freelance drivers to move the cars, for one simulated week.

- The system is `dispatch.py`, in Python, run with uv. Before you change it, read
  `docs/spread/HANDBOOK.md`. `RULES.md` and `API.md` next to it are the full references.
  `README.md` has the setup and the dates.
- **Never run online unless the user explicitly asks.** By default, do not play or read worlds
  on the Spread server. This covers every command that plays or reads worlds: `dispatch.py`,
  `pnpm dispatch`, `pnpm bench`, `pnpm tune`, `strategies.bench`, `strategies.tournament`, the scrape and reveal tools,
  and any direct call to the API. Work from the saved weeks under `data/scrape/runs/` and
  `out/spread.sqlite` instead. Only an explicit request in the current conversation lifts this.
- Practice weeks are free and repeatable: the same seed and level give the same week.
  Compare two versions of the system on the same seeds.
- Ask for approval before you play a ranking run (`--board`) or a final (`--final`). Each
  ranking world can be played once, and its score stays on the public rankings.
- Every online run is saved. When `dispatch.py` finishes a week on the server (a practice week,
  the bench's weeks, a ranking run or a final), `tools/record.py` saves it to
  `data/scrape/runs/L<level>/<seed>/<world id>/` and to the database `out/spread.sqlite`.
  Commit the new folders under `data/scrape/runs` in your PR, so the team keeps the data; each
  world has its own folder, so they never conflict. Keep the saving on, and make any new script
  that plays online save its weeks with `tools.record.Recorder` too.
- Run against the saved data, not online. Before you play a week to answer a question, build the
  database from every committed week with `uv run python -m tools.db` and query `out/spread.sqlite`
  (`tools/README.md` lists the tables). Play online only to measure a changed system, or for data that
  no saved week has.
- **One online run at a time.** An online run is any command that plays or reads
  worlds on the Spread server: `dispatch.py`, `pnpm dispatch`, `pnpm bench`, `pnpm tune`, `strategies.bench`,
  `strategies.tournament`, the scrape and reveal tools. Start a run only when your previous one has
  finished: no second run in the background or in another terminal. A bench, a tune or a tournament is
  one run, whatever its `--jobs` or `--keys`. Every system on our key shares one rate limit,
  so parallel runs slow down the whole team.

## Active models

Before you play anything on the live server, read [`active-models.md`](active-models.md). It lists the models worth a
practice week, taken from the last comparison of every system, and says how to refresh the list. Play one of those —
with the root `dispatch.py` beside it as the week's reference — rather than a model the team has already left behind,
so the eight shared practice slots and the rate limit go to the models that are ahead.

---

# Agent workflow

Rules for every coding agent working in this repository. They are stack-agnostic:
the only stack-specific part is the [Commands](#commands) list.

The loop: **issue → branch → build → PR → keep it mergeable → merged.**
Optimise for speed. Small issues, small PRs, no tests.

## 1. Start from an issue

- All work starts from a GitHub issue the user hands you, so every change is
  tracked and reviewable. If asked for a feature without one, create the issue
  first, then work from it.
- When you start on an issue, rename it so its title starts with
  `In progress: ` (e.g. `In progress: Add login form`), so everyone can see
  it is taken. Skip this if the title already starts with it.
- One issue = one feature, **including its documentation**. Both ship in the
  same PR.
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
- Pull and rebase from the default branch often: before you start, before each
  push, and whenever it has moved. Others merge all the time, and an early
  rebase keeps conflicts small:

  ```bash
  git pull --rebase origin <default-branch>
  ```

  Rebase only commits you have not pushed yet. Once a branch is pushed, merge
  the default branch into it instead (`git pull --no-rebase origin
  <default-branch>`), because a rebased branch needs a force-push.
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
- Write the issue for a reader who has not seen your work: key point first,
  plain words, full sentences, and only names that exist in the code or the UI.

## 4. Testing: not allowed

**Testing is not allowed.** This overrides any default habit of writing or
running tests.

- Do not write, add or change tests, and do not ask for them in new issues.
- Do not run tests: no `pytest`, `node --test`, `pnpm test` or any other test
  runner.
- Check your work by reading it, and with lint, format and type check from the
  Commands list.

## 5. Documentation

- Document the feature in the same PR: update the `README.md` next to the code, or the relevant page
  under `docs/`. Say what it does and how to use it — keep it short.
- If you change how the project is run or built, update the Commands
  list below in the same PR.

## 6. Pull request

Open the PR as a **draft** right after your first push, so the user can follow
the work while it is in progress. When the feature and its docs are done and
the description below is final, **move the PR from draft to open** (ready for
review). An open PR means it is ready for the user to approve without further
questions; never leave finished work in draft.

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
  force-push), resolve, push.
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

These routine steps need no approval: mark the issue you start on as
`In progress: `, create a branch or worktree, commit, push
to your own branch, open a draft PR, move your own PR from draft to open, create
follow-up issues, reply on your own PR, resolve merge conflicts, fix CI, close
the issue of your own merged or closed PR.

Ask for approval before these, because they are hard to undo or change what
other people see: merging a PR, pushing to the default branch, force-pushing,
deleting a branch, closing or editing any other issue you did not create
(beyond marking the one you start on as in progress).

## Commands

Stack-specific. The first PR that introduces or changes tooling must fill this
in and keep it current. Each item is one task and a single copy-pasteable command,
on one line, so two PRs that each add a command do not conflict.

- Install dependencies: `pnpm install`
- Lint / format: `pnpm format`
- Lint only (no writes): `pnpm lint`
- Type check: `pnpm check`
- Install Python dependencies: `uv sync`
- Play a Spread practice week: `uv run dispatch.py --level 8 --seed spread-1`
- Play an admission scenario: `uv run python strategies/admission_scenarios/capacity.py --level 8 --seed spread-1`
- Play the baseline week: `uv run python strategies/baseline/baseline.py --level 8 --seed spread-1`
- Play the price-ladder week: `uv run strategies/price_ladder/dispatch.py --level 8 --seed spread-1`
- Play the city-ladder week: `uv run strategies/city_ladder/dispatch.py --level 8 --seed spread-1`
- Play the dealer-ladder week: `uv run strategies/dealer_ladder/dispatch.py --level 8 --seed spread-1`
- Play the dealer-streak week: `uv run strategies/dealer_streak/dispatch.py --level 8 --seed spread-1`
- Play the baseline-ladder week: `uv run python strategies/baseline_ladder/baseline_ladder.py --level 8 --seed spread-1`
- Play the baseline-tiers week: `uv run python strategies/baseline_tiers/baseline_tiers.py --level 2 --seed spread-1`
- Play the streak-ladder week: `uv run strategies/streak_ladder/dispatch.py --level 8 --seed spread-1`
- Play the scarcity-priced week: `uv run strategies/scarcity_cost/dispatch.py --level 8 --seed spread-1`
- Play the more-chains week: `uv run strategies/bundling_more/dispatch.py --level 8 --seed spread-1`
- Play the cheaper-bundles week: `uv run strategies/bundling_cheaper/dispatch.py --level 8 --seed spread-1`
- Play the urgency-priced week: `uv run strategies/delivery_urgency/dispatch.py --level 8 --seed spread-1`
- Play the special-premium week: `uv run strategies/special_premium/dispatch.py --level 8 --seed spread-1`
- Play the scarcity-urgency week: `uv run strategies/scarcity_urgency/dispatch.py --level 8 --seed spread-1`
- Play the ratchet week: `uv run strategies/ratchet/dispatch.py --level 8 --seed spread-1`
- Play the ceiling-pricing week: `uv run strategies/ceiling/dispatch.py --level 8 --seed spread-1`
- Play the headroom week: `uv run strategies/headroom/dispatch.py --level 8 --seed spread-1`
- Play the learned-hold week: `uv run strategies/learned_hold/dispatch.py --level 8 --seed spread-1`
- Play the bulk-yard week: `uv run strategies/bulk_yard/dispatch.py --level 8 --seed spread-1`
- Play the lane-prior week: `uv run strategies/lane_prior/dispatch.py --level 8 --seed spread-1`
- Play the town-opening week: `uv run strategies/town_open/dispatch.py --level 8 --seed spread-1`
- Play the same-day week: `uv run strategies/same_day/dispatch.py --level 8 --seed spread-1`
- Play the soft-top week: `uv run strategies/soft_top/dispatch.py --level 8 --seed spread-1`
- Play the snow-aware week: `uv run strategies/snow_aware/dispatch.py --level 8 --seed spread-1`
- Measure the lead-cost table: `uv run python -m strategies.lead_cost.fit`
- Fit the lane fees: `uv run python -m strategies.lane_fee.fit`
- Fit the lane priors: `uv run python -m strategies.lane_prior.fit`
- Play the scarcity-ceiling week: `uv run strategies/scarcity_ceiling/dispatch.py --level 8 --seed spread-1`
- Play the profit-max week: `uv run strategies/profit_max/dispatch.py --level 8 --seed spread-1`
- Play the learned-cost week: `uv run strategies/learned_cost/dispatch.py --level 8 --seed spread-1`
- Play the trust-value week: `uv run strategies/trust_value/dispatch.py --level 8 --seed spread-1`
- Play the war-guard week: `uv run strategies/war_guard/dispatch.py --level 8 --seed spread-1`
- Play the option-menu week: `uv run strategies/option_menu/dispatch.py --level 8 --seed spread-1`
- Play the slack-fees week: `uv run strategies/slack_fees/dispatch.py --level 8 --seed spread-1`
- Play the tempo week: `uv run strategies/tempo/dispatch.py --level 8 --seed spread-1`
- Play the max-margin week: `uv run strategies/max_margin/dispatch.py --level 8 --seed spread-1`
- Play the tight-margin week: `uv run strategies/tight_margin/dispatch.py --level 8 --seed spread-1`
- Play the low-opening week: `uv run strategies/low_opening/dispatch.py --level 8 --seed spread-1`
- Play the opening-offers week: `uv run strategies/opening_offers/dispatch.py --level 8 --seed spread-1`
- Play the home-return week: `uv run strategies/home_return/dispatch.py --level 8 --seed spread-1`
- Play the adaptive-fees week: `uv run strategies/adaptive_fees/dispatch.py --level 8 --seed spread-1`
- Play the hazard-admission week: `uv run strategies/hazard_admission/dispatch.py --level 8 --seed spread-1`
- Play the ifs week: `uv run strategies/ifs/dispatch.py --level 8 --seed spread-1`
- Search the ifs values for better weeks: `uv run python -m strategies.ifs.search --target 20000`
- Write an ended week to CSV: `uv run spread-reveal-csv <world id>`
- Measure the note reader: `uv run python -m strategies.notes.check reveal-<world id>`
- Compare two versions: `uv run python -m strategies.bench dispatch.py origin/main`
- Play a mix of the changes built on ceiling: `uv run strategies/tournament/mix.py --layers slack_fees,tempo --level 8 --seed spread-1`
- See what a tournament would play (plays nothing): `uv run python -m strategies.tournament --plan`
- Play the tournament of ceiling's layers: `uv run python -m strategies.tournament --seeds spread-1..spread-3`
- Play the active models on fresh seeds until stopped: `uv run python -m tools.sweep`
- List open worlds older than 15 minutes (`--yes` deletes them): `uv run --env-file .env python -m tools.kill_old_worlds`
- Build the saved-weeks DB: `uv run python -m tools.db`
- Lint / format Python: `uv run ruff check --fix . && uv run ruff format .`
- Play a week in TypeScript: `pnpm dispatch --level 8 --seed spread-1`
- Write a week to CSV (TS): `pnpm reveal-csv <world id>`
- Compare TypeScript strategies: `pnpm bench starter --level 8 --seeds spread-1..spread-5`
- Tune a TypeScript strategy's params: `pnpm tune <strategy> --space <space.json> --holdout spread-6..spread-10`
- Build the facts tables: `uv run python -m analysis.facts`
- Build the quotas database: `uv run python -m analysis.quotas`
- Export the fee model priors: `uv run python -m analysis.priors_fees`
- Margin gap report (oracle): `uv run python -m analysis.oracle`
- Get the team's scraped data: `mkdir -p out && gh release download --pattern 'spread-data-*.tar.gz' --output - | tar -xz -C out`
- Build and serve the report: `uv run python -m analysis.report`
- Build the report file only: `uv run python -m analysis.report --no-serve`
- Replay the strategies offline and serve the charts: `uv run python -m analysis.replay`
- Write the replay files only: `uv run python -m analysis.replay --no-serve`
- Export the quote priors: `uv run python -m analysis.priors_quote`
- Replay the quote models on the probes: `node analysis/replay_quote.ts`
- Split saved weeks' margin by the hour an order was won: `uv run python -m analysis.phases`

## Definition of done

- [ ] Feature works as the issue describes
- [ ] No tests written or run
- [ ] Documentation updated
- [ ] Follow-up work filed as new issues
- [ ] PR moved from draft to open (ready for review), description ≤ 500 characters, `Closes #<issue>`
- [ ] No conflicts, CI green
