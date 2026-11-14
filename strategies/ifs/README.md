# The ifs system

A basic dispatch system. Every decision on a price request is a plain `if` over one of the request's inputs, and
every number those rules use is in one file, [`values.json`](values.json). So a rule changes without a code edit, and
a search changes the numbers for us: it plays practice weeks until the margin is over a target. Issue #212.

Its rules take the place of the root desk's admission and pricing, and its fees plan each gig's fee schedule.
Everything else (the loop, posting, notes, retries, bundling, direct offers, the final) is the root `dispatch.py`,
which stays as it is.

| File          | Class     | Builds on        | What it holds                                                      |
| ------------- | --------- | ---------------- | ------------------------------------------------------------------ |
| `values.json` |           |                  | Every number of the rules, with the range and step the search uses |
| `rules.py`    | `IfRules` | `Strategy`       | The rules for a price request: take it or not, and at what price   |
| `fees.py`     | `IfFees`  | `LaneFeePlanner` | The numbers of a gig's fee schedule, and two rules for its opening |
| `dispatch.py` | `Desk`    | the root `Desk`  | The system: the root desk with the rules and fees above            |
| `search.py`   |           | the seed bench   | The search for better values                                       |

## Run it

From the repository root, with the options of the root `dispatch.py` (`--level`, `--seed`, `--board`, `--final`) and
one more, `--values`:

```sh
uv run strategies/ifs/dispatch.py --level 8 --seed spread-1                                # the values of values.json
uv run strategies/ifs/dispatch.py --level 8 --seed spread-1 --values out/ifs/best.json     # the values of another file
uv run python -m strategies.bench strategies/ifs/dispatch.py strategies/headroom/dispatch.py --jobs 4
```

Its weeks are saved like the root system's (`tools/record.py`), with the policy `ifs` and, in `meta.json` under
`settings`, every value the week was played with. At the end of a practice week the rules print a line:

```text
Ifs: 741 of 1036 requests quoted (383 next day, 357 same day, 1 within 3 days), 286 won; declined 41 for time, 25 for room, 229 for cost; 204 quotes at the cost floor; usual price x1.34, the most we ask x1.45
```

## Change a value

Each entry of `values.json` is one number of one rule:

```json
"fee_open": { "value": 0.9, "min": 0.5, "max": 1.3, "step": 0.1 },
```

- Change `value` and play a week: that is the whole change. The tables below say what each value does.
- `min`, `max` and `step` are for the search: it moves the value by `step` inside the range. An entry without a
  `step` is a value the search leaves alone; `"whole": true` keeps a value a whole number.
- To try values without touching `values.json`, write them in another file and name it with `--values`. That file
  holds some of the names or all of them, as plain numbers: `{ "fee_open": 0.8, "price_base": 1.45 }`.

## The rules for a price request

`IfRules.quote` in `rules.py` answers each request in five steps. It quotes one option at one price.

1. **Time.** An option counts when it leaves `slack_hours_least` between the car's ready time and its deadline,
   beyond the drive. If none does, we decline.
2. **Room.** We count our cars near the pickup that still need a driver that day, and our quotes there that the
   dealer has not answered. If one more does not fit in the area's room, we decline.
3. **The cost of each option.** What we expect to pay drivers when the dealer takes that option: the typical fee
   times `cost_base`, times one factor for each `if` that fits (the cost table below).
4. **The price of each option.** The usual price, times one factor for each `if` that fits (the price table below),
   and never less than the cost times (1 + `min_margin`). An option whose cost with that margin is above the most we
   ask drops out.
5. **The option.** Of the options left, we quote the one whose price leaves the most money after its cost. If none
   is left, we decline.

To decline, the desk quotes ten times the list price, which loses at no cost.

**The typical fee** is the lane's: the mean typical fee of the lane's requests in the saved weeks
([`strategies/lane_fee`](../lane_fee/README.md)), which leaves out the noise in one request's own number. `lane_fee`
set to 0 counts from the request's own typical fee instead.

**The usual price** is `price_base` times a ladder, which starts at 1. A won quote raises the ladder by `ladder_up`
and a lost one lowers it by `ladder_down`, so the price follows what this world's dealers accept. A quote that the
cost floor priced and lost teaches nothing: our cost lost it, not our price.

**The most we ask** is `price_base` times a cap, which also starts at 1, times the factors of the rules that fit. The
ladder never rises above the cap. A won quote at the cap raises the cap by `cap_step` and a lost one lowers it, between
`cap_min` and `cap_max`: where dealers take the most we ask, we ask more.

Two rules watch runs of outcomes in the working hours (08:00 to 18:00) of one day:

- **The price war.** `war_losses` lost quotes in a row, from Tuesday on, are the competitor's price war. Until 18:00
  the usual price is `price_war` times what it was before the run, and that day's outcomes teach nothing.
- **The outage.** `outage_wins` won quotes in a row at one pickup place are the outage there: dealers turn to a backup
  that costs more. Until 18:00 its requests are priced `price_outage` times higher. Two lost quotes in a row at that
  price end it. Wins at the cap do not count: there we expect to win.

### The price

| Value                                | The rule                                                                                 |
| ------------------------------------ | ---------------------------------------------------------------------------------------- |
| `price_base`                         | Every quote starts at the list price times this                                          |
| `ladder_up`, `ladder_down`           | A won quote raises the usual price by this share, a lost one lowers it                   |
| `ladder_min`                         | The ladder never falls below this                                                        |
| `cap_step`, `cap_min`, `cap_max`     | The cap moves by this share with each outcome at it, between these; 0 holds it at 1      |
| `dealer_step`                        | Each dealer has its own factor, moved by this share by its own wins and losses; 0 is off |
| `place_step`                         | The same for each pickup place and each delivery place                                   |
| `trust_use`                          | Level 8, if the dealer trusts us: + this share of its trust (1% an order on time)        |
| `price_same_day`, `price_three_days` | If the option is same day, or within three days: times this                              |
| `short_km`, `price_short`            | If the cars travel less than `short_km` by road: times `price_short`                     |
| `long_km`, `price_long`              | If they travel more than `long_km`: times `price_long`                                   |
| `price_monday`                       | If the request comes on Monday, before any dealer trusts us: times this                  |
| `price_batch`                        | If the request is one of a batch from one dealer: times this                             |
| `war_losses`, `price_war`            | The price war, above                                                                     |
| `outage_wins`, `price_outage`        | The outage, above                                                                        |

### The cost

The first five rows after `cost_base` are one chain of `if` and `else if` on how long the car can wait for its
driver: the first that fits counts. The lead is the hours from the dealer's decision to the last minute the car can
be collected and still arrive by the option's deadline, inside the pickup site's hours. They apply at levels 7 and 8,
the shortage.

| Value                                          | The rule                                                                         |
| ---------------------------------------------- | -------------------------------------------------------------------------------- |
| `cost_base`                                    | The typical fee times this, at levels 7 and 8                                    |
| `lead_tight_hours`, `cost_lead_tight`          | If the lead is under `lead_tight_hours`: times `cost_lead_tight`                 |
| `lead_short_hours`, `cost_lead_short`          | Else if it is under `lead_short_hours`: times `cost_lead_short`                  |
| `ready_later_hours`, `cost_ready_later`        | Else if the car is ready this many hours after the decision, or later: × this    |
| `ready_soon_hours`, `cost_ready_soon`          | Else if it is ready `ready_soon_hours` after it, or later: times this            |
| `lead_day_hours`, `cost_lead_day`              | Else if the lead is under `lead_day_hours`: times `cost_lead_day`                |
| `cost_far_pickup`, `drivers_scale`             | Times 1 + `cost_far_pickup` × e^(−drivers near the pickup / `drivers_scale`)     |
| `cost_far_delivery`                            | The same for the drivers near the delivery                                       |
| `cost_same_day`                                | If the option is same day: times this                                            |
| `cost_short`, `cost_long`                      | If the cars travel less than `short_km`, or more than `long_km`: times this      |
| `cost_private_pickup`, `cost_private_delivery` | If a car waits at a private address, or goes to one: times this                  |
| `cost_trade_in`                                | If the request has two cars: times this                                          |
| `cost_premium`                                 | If a car is premium, which needs an experienced driver: times this               |
| `cost_charging`                                | If an electric car is under 30%, so the driver stops to charge: times this       |
| `cost_batch`                                   | If the request is one of a batch: times this                                     |
| `cost_note`                                    | If the note asks for something a driver can miss (gearbox, plates, a time): this |
| `evening_hour`, `cost_evening`                 | If the car is ready at `evening_hour` or later: times `cost_evening`             |
| `cost_weekend`                                 | If the car is ready on Saturday or Sunday: times this                            |
| `cost_friday`                                  | If the request comes on Friday: times this                                       |
| `min_margin`                                   | The floor of step 4: the cost times (1 + this)                                   |

### Room and time

| Value                             | The rule                                                                                   |
| --------------------------------- | ------------------------------------------------------------------------------------------ |
| `slack_hours_least`               | Step 1: the hours an option must leave beyond the drive                                    |
| `room_per_driver`, `room_least`   | An area has room for this many waiting cars for each driver near it, and at least so many  |
| `on_time_guard`, `room_when_late` | If our share of orders on time is under `on_time_guard`: the room times `room_when_late`   |
| `reach_minutes`                   | A driver counts as near by e^(−road minutes from home / this): 1 at the place, less beyond |
| `area_minutes`                    | The area of step 2: pickups within this many road minutes                                  |

For a premium car, the drivers near are the experienced ones (rating 4.8 or more, 50 gigs or more). Up to level 3
every quote wins the first option at its list price, so there the rules only decide whether to quote it.

## The rules for a fee schedule

The schedule is the dawn schedule of [`strategies/dawn_fees`](../dawn_fees/README.md), which follows the drivers' day,
with every number from `values.json`. Each fee is a multiple of the typical fee, the lane's as above.

- **A gig with a morning before its last pickup** opens low, rises once, holds that fee through the evening and the
  night, and climbs from dawn on its last morning, when the drivers plan their day.
- **A gig with no morning to wait for** climbs a short ladder to the top fee: the sprint.
- With less than `fee_reach_hours` left, for a late car and at level 1, the schedule is that of `strategies/fees`.

| Value                                 | The rule                                                                             |
| ------------------------------------- | ------------------------------------------------------------------------------------ |
| `fee_open`                            | The opening fee: the typical fee times this                                          |
| `fee_open_short`, `fee_open_private`  | If the cars travel less than `short_km`, or one waits at a private address: × this   |
| `fee_hold`, `fee_patience_hours`      | After `fee_patience_hours` the fee rises to `fee_hold`, and holds until the dawn     |
| `fee_dawn`, `fee_dawn_hour`           | At `fee_dawn_hour` on the last morning the fee is `fee_dawn`, then it climbs         |
| `fee_step_hours`                      | The climb from the dawn fee to the top fee has one step each this many hours         |
| `fee_top`                             | The top fee, due a travel margin of 6 to 8 hours before the last pickup              |
| `fee_reach_hours`                     | A driver who books at dawn needs this long to reach the car: the last dawn is before |
| `fee_tight`, `fee_evening_hour`       | If the top is due before that dawn: `fee_tight` at `fee_evening_hour` the day before |
| `fee_quiet_hour`                      | No raise on the day of the post from this hour on                                    |
| `fee_sprint_open`, `fee_sprint_hours` | The sprint opens at `fee_sprint_open` and reaches the top within `fee_sprint_hours`  |
| `fee_sprint_step_minutes`             | The sprint has one step each this many minutes                                       |

No fee before the top goes above the order's price, and the top is cut where a late car would cost less, as in
`strategies/fees`. A gig with several orders' cars keeps the root desk's schedule.

## The search

`search.py` looks for better values by playing practice weeks, as one online run:

```sh
uv run --env-file .env python -m strategies.ifs.search                              # until a week earns over €20,000
uv run --env-file .env python -m strategies.ifs.search --seeds spread-1 --target 12000 --confirm none
uv run python -m strategies.ifs.search --dry                                        # what it would play; no server
uv run python -m strategies.ifs.search --adopt out/ifs/best.json                    # the best values into values.json
```

1. It plays the seeds with the starting values. The score of a set of values is the mean margin of its weeks.
2. It goes through the values that have a `step`, in the order of `values.json`. For each it plays the same seeds
   with the value one step up and one step down, both in one bench run.
3. If the better of the two beats the best score by more than `--min-gain`, it plays that set and the best set on
   the `--confirm` seeds too. Only if it gains more than `--min-gain` there as well, it keeps the change and stays on
   the value, so the next step goes on in the same direction. Else it moves to the next value.
4. A pass that kept a change is followed by another. A pass that kept nothing halves every step, down to a quarter.
5. When the quarter steps keep nothing either, it tries `--jumps` changes of two or three values at once. A kept jump
   starts the passes again; if no jump is kept, the search stops and says so.
6. It stops when the best mean margin is over `--target`.

**Why it confirms.** The same seed moves by hundreds of euros between two sets of values that differ little: a
booking a minute earlier changes which driver is free for the next car. In the first search, steps of two values
that should matter little moved the mean of three weeks by −€317 and −€332. A gain on the seeds that picked a change
is partly luck, and the confirm seeds had no part in picking it. So the steps in `values.json` are large: a step
whose effect is smaller than that noise cannot be told from it.

A week that is not ranked, or under `--min-on-time`, never counts as better: its values lose to any values without
such a week. The search plays practice weeks only, never a ranking run or a final, through the seed bench
(`strategies/bench`), so it frees its worlds when stopped. It is one online run, whatever its `--jobs`: do not start
it while another run is going.

| Option          | Default                      | What it does                                                             |
| --------------- | ---------------------------- | ------------------------------------------------------------------------ |
| `--target`      | `20000`                      | Stop when the mean margin of a week is over this many euros              |
| `--seeds`       | `spread-1,spread-2,spread-3` | The seeds every set of values plays. A range works: `spread-1..spread-5` |
| `--confirm`     | `spread-4,spread-5,spread-6` | The seeds a change must gain on too before it is kept, or `none`         |
| `--level`       | `8`                          | The practice level                                                       |
| `--jobs`        | `6`                          | Weeks played at once. Six leaves two practice slots to teammates         |
| `--values`      | `values.json`                | A file of values to start a new search from                              |
| `--only`        | every value with a step      | Search only these values, comma-separated                                |
| `--min-on-time` | `0.93`                       | The on-time share under which a week never counts as better              |
| `--min-gain`    | `150`                        | Keep a change only when it raises the mean margin by more than this      |
| `--max-weeks`   | `0`, no limit                | Stop after playing this many weeks                                       |
| `--jumps`       | `12`                         | Changes of several values to try when no single value helps              |
| `--holdout`     | none                         | Seeds to play the best and the starting values on at the end             |
| `--state`       | `out/ifs/search.json`        | The file that keeps the search                                           |
| `--fresh`       |                              | Start a new search; the old state file is kept under another name        |
| `--stop-file`   | `out/ifs/stop`               | The search stops when this file exists, read between steps               |
| `--dry`         |                              | Print the values and the weeks of one pass, and play nothing             |
| `--adopt FILE`  |                              | Write the values of the file into `values.json`, and play nothing        |

**Stop and go on.** Stop it with Ctrl-C, or create `out/ifs/stop` to let the step in play end first; delete that
file before the next run. The same command then goes on from `out/ifs/search.json`. Other seeds or another level
need `--fresh`, or another `--state`.

**Edit while it runs.** When a search starts, it copies the code that plays a week to `out/ifs/code/` and plays
every week with that copy. So the rules can be edited while a search runs: the search in play keeps its code, and the
next start plays the new code, beginning with the best values again.

**Keep the computer awake.** A week that cannot reach the server fails, and the search plays its step again after a
pause, up to eight times. A closed laptop lid stops it all the same. On a Mac, `caffeinate -i` in front of the command
keeps the computer from idle sleep while the search runs.

**What it writes**, all under `out/ifs/`, which is not committed:

- `best.json`: every value of the best set so far, rewritten at each kept change. Play it with `--values`, or make it
  the system's values with `--adopt`, which changes only the numbers in `values.json`.
- `search.json`: the state, with every set of values tried and its score.
- `weeks.json`: the score of every week played, by seed and values, so the same week is never played twice, also by
  a later search. A week played before the code of the system changed is played again.
- `trials/`: the values file of each set tried.
- `code/`: the copies of the code, one for each version of it that a search played.

**What it costs.** `--dry` prints the count: with the 65 values that have a step and three seeds, a pass is at most
390 weeks, and the confirm seeds add six weeks for each change that gets that far. A week takes 15 to 45 seconds, so
six at a time is about half an hour a pass on a quiet server, and longer when the team's rate limit is shared.

**Where its weeks go.** Every week is saved, as any online run is, but a search plays hundreds, about 0.4 MB each.
So it saves them as folders under `out/scrape/ifs-search/`, outside git and outside `out/spread.sqlite`
(`SPREAD_RUNS_DIR` names another folder). When it stops, it copies the weeks of the best and of the starting values
to `data/scrape/runs`: commit those with the PR. `uv run python -m tools.db out/scrape/ifs-search` loads every week
of the search into the database when they are wanted.

**Read the result with care.** The search keeps what did best on its seeds, so its best score flatters the values.
`--holdout` plays the best and the starting values on seeds that neither picked nor confirmed a change, and that
table is the fair comparison. The best saved level 8 week of any system is €13,976, so the default target of €20,000
is far away: the search runs until it gets there, is stopped, or finds no better week.

## Where the starting values come from

The rules started close to [`strategies/ceiling`](../ceiling/README.md). Their second version, the one here, takes
what the systems of issue #200 measured on the saved weeks, as plain rules with their numbers in `values.json`:

- **The cost by lead time** ([`strategies/lead_cost`](../lead_cost/README.md)). A car to collect within 8 hours cost
  2.4 times its typical fee, within 14 hours 1.77 times, and a car ready the next day 1.03 times. The five lead
  rules are that table: `cost_base` 1.25 for a car that is ready now with a day or more to collect it, times 1.92,
  1.42, 0.83, 0.88 or 1.15. The factors for the drivers near both ends, a private address, a short trip, a premium
  car and a note are that folder's too.
- **The option of the most margin** (the same folder), in place of the fastest option with nine hours to spare.
- **The cap that moves** ([`strategies/headroom`](../headroom/README.md)): 0.6% up after a won quote at it and 0.6%
  down after a lost one, between 1.20 and 1.62 times the list price, with the ladder aiming a little under half of
  its quotes won.
- **The dawn schedule on the lane fee** ([`strategies/dawn_fees`](../dawn_fees/README.md),
  [`strategies/lane_fee`](../lane_fee/README.md)), and room for twice the waiting cars, because a gig that waits for
  its morning is not a sign that an area is full.

Four things differ from the headroom system: a trade-in costs `cost_trade_in` more (46% of the saved trade-ins
arrived on time), the price war and the outage are found by runs of losses and wins, no car counts as a return leg,
and only the dealer has an own price factor until `place_step` is above 0.

## Results

Level 8, seeds `spread-1` to `spread-3`, played on 2026-11-14 as the first step of a search, each week saved in
`data/scrape/runs/L8/` with the policy `ifs`. The first version of the rules was the ceiling system's; the second is
described above. Beside them are the saved weeks of `ceiling` and `slack_fees` on the same seeds, from their READMEs.

| Seed       | Rules, first version | Rules, second version | Orders | On time |    Ceiling | Slack fees |
| ---------- | -------------------: | --------------------: | -----: | ------: | ---------: | ---------: |
| `spread-1` |           €10,546.00 |            €12,104.57 |    369 |   98.9% |  €9,831.09 | €10,206.83 |
| `spread-2` |            €7,374.60 |             €8,926.25 |    291 |   99.0% |  €6,673.95 |  €6,891.04 |
| `spread-3` |            €4,330.40 |             €4,682.29 |    231 |   96.1% |  €4,312.02 |  €4,077.60 |
| Total      |           €22,251.00 |            €25,713.11 |    891 |   98.2% | €20,817.06 | €21,175.47 |

The orders and the on-time share are the second version's. It earns €4,896 more than `ceiling` over the three weeks,
more on each seed, and every week is ranked. On `spread-1` and `spread-2` the headroom system made €12,670.71 and
€9,378.79, so the second version is close to it and under it.

The first search, on the first version of the rules, kept two changes in 51 weeks (`ladder_up` 0.015 to 0.01 and a
maximum of 1.04 times `price_base`) for a mean of €7,906.57 a week against €7,417.00. Its other steps showed how much
a week moves by chance, which is why the search now confirms a change on other seeds.
