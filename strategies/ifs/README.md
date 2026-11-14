# The ifs system

A basic dispatch system. Every decision on a price request is a plain `if` over one of the request's inputs, and
every number those rules use is in one file, [`values.json`](values.json). So a rule changes without a code edit, and
a search changes the numbers for us: it plays practice weeks until the margin is over a target. Issue #212.

Its rules take the place of the root desk's admission and pricing, and its fees plan each gig's fee schedule.
Everything else (the loop, posting, notes, retries, bundling, direct offers, the final) is the root `dispatch.py`,
which stays as it is.

| File          | Class     | Builds on       | What it holds                                                      |
| ------------- | --------- | --------------- | ------------------------------------------------------------------ |
| `values.json` |           |                 | Every number of the rules, with the range and step the search uses |
| `rules.py`    | `IfRules` | `Strategy`      | The rules for a price request: take it or not, and at what price   |
| `fees.py`     | `IfFees`  | `FeePlanner`    | The rules for a gig's fee schedule                                 |
| `dispatch.py` | `Desk`    | the root `Desk` | The system: the root desk with the rules and fees above            |
| `search.py`   |           | the seed bench  | The search for better values                                       |

## Run it

From the repository root, with the options of the root `dispatch.py` (`--level`, `--seed`, `--board`, `--final`) and
one more, `--values`:

```sh
uv run strategies/ifs/dispatch.py --level 8 --seed spread-1                                # the values of values.json
uv run strategies/ifs/dispatch.py --level 8 --seed spread-1 --values out/ifs/best.json     # the values of another file
uv run python -m strategies.bench strategies/ifs/dispatch.py strategies/ceiling/dispatch.py --jobs 4
```

Its weeks are saved like the root system's (`tools/record.py`), with the policy `ifs` and, in `meta.json` under
`settings`, every value the week was played with. At the end of a practice week the rules print a line:

```text
Ifs: 639 of 1037 requests quoted, 357 won; declined 40 for time, 68 for room, 290 for cost; 73 quotes at the cost floor; usual price x1.26
```

## Change a value

Each entry of `values.json` is one number of one rule:

```json
"fee_open": { "value": 0.9, "min": 0.5, "max": 1.3, "step": 0.05 },
```

- Change `value` and play a week: that is the whole change. The tables below say what each value does.
- `min`, `max` and `step` are for the search: it moves the value by `step` inside the range. An entry without a
  `step` is a value the search leaves alone; `"whole": true` keeps a value a whole number.
- To try values without touching `values.json`, write them in another file and name it with `--values`. That file
  holds some of the names or all of them, as plain numbers: `{ "fee_open": 0.8, "price_base": 1.45 }`.

## The rules for a price request

`IfRules.quote` in `rules.py` answers each request in five steps. Each quotes one option at one price.

1. **The option.** The fastest option that leaves `slack_hours` between the car's ready time and the deadline, beyond
   the drive. If none does, the slowest option when it leaves `slack_hours_least`. Else we decline.
2. **Room.** We count our cars near the pickup that still need a driver that day, and our quotes there that the
   dealer has not answered. If one more does not fit in the area's room, we decline.
3. **The cost.** What we expect to pay drivers: the typical fee times `cost_base`, times one factor for each `if`
   that fits (the cost table below).
4. **The price.** The usual price, times one factor for each `if` that fits (the price table below).
5. **The floor.** We never ask less than the cost times (1 + `min_margin`). If the usual price is lower, we quote
   that floor. If the floor is above the most we ask, we decline.

To decline, the desk quotes ten times the list price, which loses at no cost.

**The usual price** is `price_base` times a ladder, which starts at 1. A won quote raises the ladder by `ladder_up`
and a lost one lowers it by `ladder_down`, so the price follows what this world's dealers accept. It stays between
`ladder_min` and `ladder_max`, and the most we ask is `price_base` × `ladder_max`, times the factors of the rules that
fit. A quote that the cost floor priced and lost teaches nothing: our cost lost it, not our price.

Two rules watch runs of outcomes in the working hours (08:00 to 18:00) of one day:

- **The price war.** `war_losses` lost quotes in a row, from Tuesday on, are the competitor's price war. Until 18:00
  the usual price is `price_war` times what it was before the run, and that day's outcomes teach nothing.
- **The outage.** `outage_wins` won quotes in a row at one pickup place are the outage there: dealers turn to a backup
  that costs more. Until 18:00 its requests are priced `price_outage` times higher. Two lost quotes in a row at that
  price end it. Wins at the most we ask do not count: there we expect to win.

### The price

| Value                                | The rule                                                                                 |
| ------------------------------------ | ---------------------------------------------------------------------------------------- |
| `price_base`                         | Every quote starts at the list price times this                                          |
| `ladder_up`, `ladder_down`           | A won quote raises the usual price by this share, a lost one lowers it                   |
| `ladder_max`, `ladder_min`           | The ladder stays between these                                                           |
| `dealer_step`                        | Each dealer has its own factor, moved by this share by its own wins and losses; 0 is off |
| `trust_use`                          | Level 8, if the dealer trusts us: + this share of its trust (1% an order on time)        |
| `price_same_day`, `price_three_days` | If the option is same day, or within three days: times this                              |
| `short_km`, `price_short`            | If the cars travel less than `short_km` by road: times `price_short`                     |
| `long_km`, `price_long`              | If they travel more than `long_km`: times `price_long`                                   |
| `price_monday`                       | If the request comes on Monday, before any dealer trusts us: times this                  |
| `price_batch`                        | If the request is one of a batch from one dealer: times this                             |
| `war_losses`, `price_war`            | The price war, above                                                                     |
| `outage_wins`, `price_outage`        | The outage, above                                                                        |

### The cost

| Value                                          | The rule                                                                           |
| ---------------------------------------------- | ---------------------------------------------------------------------------------- |
| `cost_base`                                    | The typical fee times this, at levels 7 and 8                                      |
| `cost_far_pickup`, `drivers_scale`             | Times 1 + `cost_far_pickup` × e^(−drivers near the pickup / `drivers_scale`)       |
| `cost_far_delivery`                            | The same for the drivers near the delivery                                         |
| `cost_same_day`                                | If the option is same day: times this                                              |
| `cost_short`, `cost_long`                      | If the cars travel less than `short_km`, or more than `long_km`: times this        |
| `cost_private_pickup`, `cost_private_delivery` | If a car waits at a private address, or goes to one: times this                    |
| `cost_trade_in`                                | If the request has two cars: times this                                            |
| `cost_premium`                                 | If a car is premium, which needs an experienced driver: times this                 |
| `cost_charging`                                | If an electric car is under 30%, so the driver stops to charge: times this         |
| `cost_batch`                                   | If the request is one of a batch: times this                                       |
| `cost_note`                                    | If the note asks for something a driver can miss (gearbox, plates, a time): × this |
| `evening_hour`, `cost_evening`                 | If the car is ready at `evening_hour` or later: times `cost_evening`               |
| `cost_weekend`                                 | If the car is ready on Saturday or Sunday: times this                              |
| `cost_friday`                                  | If the request comes on Friday: times this                                         |
| `min_margin`                                   | The floor of step 5: the cost times (1 + this)                                     |

### Room and time

| Value                              | The rule                                                                                   |
| ---------------------------------- | ------------------------------------------------------------------------------------------ |
| `slack_hours`, `slack_hours_least` | Step 1: the hours an option must leave beyond the drive                                    |
| `room_per_driver`, `room_least`    | An area has room for this many waiting cars for each driver near it, and at least so many  |
| `on_time_guard`, `room_when_late`  | If our share of orders on time is under `on_time_guard`: the room times `room_when_late`   |
| `reach_minutes`                    | A driver counts as near by e^(−road minutes from home / this): 1 at the place, less beyond |
| `area_minutes`                     | The area of step 2: pickups within this many road minutes                                  |

For a premium car, the drivers near are the experienced ones (rating 4.8 or more, 50 gigs or more). Up to level 3
every quote wins the first option at its list price, so there the rules only decide whether to quote it.

## The rules for a fee schedule

`plan` in `fees.py` plans each gig's fees from the minute it is posted: an opening fee, two raises and a top fee,
each a multiple of the typical fee. The fees after a drop and at level 1 are those of `strategies/fees`.

| Value                                 | The rule                                                                                                |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `fee_open`                            | The opening fee: the typical fee times this                                                             |
| `fee_open_short`, `fee_open_private`  | If the cars travel less than `short_km`, or one waits at a private address: × this                      |
| `fee_raise_1`, `fee_raise_1_hours`    | The first raise: to the typical fee × `fee_raise_1`, this many hours after the post                     |
| `fee_raise_2`, `fee_raise_2_hours`    | The second raise, the same way                                                                          |
| `fee_top`, `fee_top_hours`            | The top fee: the typical fee × `fee_top`, due `fee_top_hours` before the last pickup                    |
| `fee_urgent_hours`                    | If the top is due sooner than this: every fee moves towards the top, in proportion                      |
| `fee_patient_hours`, `fee_hold_hours` | If the top is `fee_patient_hours` away or more: the second raise waits until `fee_hold_hours` before it |

The last rule is for a car that can wait: a driver who plans the pickup day the evening before still sees the early
fee. No fee before the top goes above the order's price, and the top is cut where a late car would cost less, as in
`strategies/fees`. With little time left the raises come sooner: at the latest a third and two thirds of the way to
the top. A step due at night comes at 22:00 the evening before.

## The search

`search.py` looks for better values by playing practice weeks, as one online run:

```sh
uv run --env-file .env python -m strategies.ifs.search                              # until a week earns over €20,000
uv run --env-file .env python -m strategies.ifs.search --seeds spread-1 --target 12000
uv run python -m strategies.ifs.search --dry                                        # what it would play; no server
uv run python -m strategies.ifs.search --adopt out/ifs/best.json                    # the best values into values.json
```

1. It plays the seeds with the starting values. The score of a set of values is the mean margin of its weeks.
2. It goes through the values that have a `step`, in the order of `values.json`. For each it plays the same seeds
   with the value one step up and one step down, both in one bench run.
3. If the better of the two beats the best score by more than `--min-gain`, it keeps that change and stays on the
   value, so the next step goes on in the same direction. Else it moves to the next value.
4. A pass that kept a change is followed by another. A pass that kept nothing halves every step, down to a quarter.
5. When the quarter steps keep nothing either, it tries `--jumps` changes of two or three values at once. A kept jump
   starts the passes again; if no jump is kept, the search stops and says so.
6. It stops when the best mean margin is over `--target`.

A week that is not ranked, or under `--min-on-time`, never counts as better: its values lose to any values without
such a week. The search plays practice weeks only, never a ranking run or a final, through the seed bench
(`strategies/bench`), so it frees its worlds when stopped. It is one online run, whatever its `--jobs`: do not start
it while another run is going.

| Option          | Default                      | What it does                                                             |
| --------------- | ---------------------------- | ------------------------------------------------------------------------ |
| `--target`      | `20000`                      | Stop when the mean margin of a week is over this many euros              |
| `--seeds`       | `spread-1,spread-2,spread-3` | The seeds every set of values plays. A range works: `spread-1..spread-5` |
| `--level`       | `8`                          | The practice level                                                       |
| `--jobs`        | `6`                          | Weeks played at once. Six leaves two practice slots to teammates         |
| `--values`      | `values.json`                | A file of values to start a new search from                              |
| `--only`        | every value with a step      | Search only these values, comma-separated                                |
| `--min-on-time` | `0.93`                       | The on-time share under which a week never counts as better              |
| `--min-gain`    | `50`                         | Keep a change only when it raises the mean margin by more than this      |
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

**What it writes**, all under `out/ifs/`, which is not committed:

- `best.json`: every value of the best set so far, rewritten at each kept change. Play it with `--values`, or make it
  the system's values with `--adopt`, which changes only the numbers in `values.json`.
- `search.json`: the state, with every set of values tried and its score.
- `weeks.json`: the score of every week played, by seed and values, so the same week is never played twice, also by
  a later search. A week played before the code of the system changed is played again.
- `trials/`: the values file of each set tried.

**What it costs.** `--dry` prints the count: with the 54 values that have a step and three seeds, a pass is at most
324 weeks. A saved week of the ceiling systems took about 30 seconds, so six at a time is about half an hour a pass
on a quiet server, and longer when the team's rate limit is shared. Every week is saved like any other online run,
about 0.4 MB each under `data/scrape/runs`; `SPREAD_RUNS_DIR` names another folder.

**Read the result with care.** The search keeps what did best on its seeds, so its best score flatters the values:
some of the gain is luck on those weeks. `--holdout` plays the best and the starting values on seeds the search did
not see, and that table is the fair comparison. The best saved level 8 week of any system is €13,716, so the default
target of €20,000 is far away: the search runs until it gets there, is stopped, or finds no better week.

## Where the starting values come from

The values in `values.json` start close to [`strategies/ceiling`](../ceiling/README.md) with the fees of
[`strategies/slack_fees`](../slack_fees/README.md): a price of 1.39 times the list price under a ladder of 1.5% a
quote, a cost of 1.15 times the typical fee with the same factors for evening, weekend and note, room for 0.10 cars
for each driver near, and fees from 0.9 to 2.5 times the typical fee. Four cost factors come from the saved weeks of
the ceiling systems, where a private pickup paid 1.75 times its typical fee, a private delivery 1.33 and a trip under
50 km 1.51, against 1.17 overall, and 46% of the trade-ins arrived on time.

Checked offline, on the 32 saved level 8 weeks of `ceiling`, `war_guard`, `slack_fees`, `tempo` and `learned_cost`:
each week's events were fed to this desk, and the orders that the week won were split by what these rules do with
their request. The margins are what those orders earned in the saved weeks, not a forecast.

| The rules               | Orders a week | Margin an order in the saved week |
| ----------------------- | ------------: | --------------------------------: |
| quote the request too   |         294.9 |                            €23.17 |
| decline it for its cost |          29.5 |                             €0.72 |
| decline it for room     |           5.3 |                            €21.78 |

Of the orders declined for cost, 17 a week are private pickups, which lost €7.37 an order.

## Results

Not played online yet: the system and the search are new. The first search adds its weeks and this section's table.
