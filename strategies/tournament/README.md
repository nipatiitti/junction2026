# Tournament

Finds the system with the best practice week among [`ceiling`](../ceiling/README.md) and the changes built on it, by
playing them on the same seeds and by playing several of the changes at once (#209). It has two parts:

- **The mixed system**, `mix.py`: the ceiling system with any set of those changes in the same week.
- **The tournament**, `python -m strategies.tournament`: plays line-ups of those changes in rounds, and stacks the
  changes that win into one system.

Both play practice weeks only. Neither plays a ranking run (`--board`) or a final by itself; `mix.py` takes `--final`
as every system does, once the team has picked it.

## Run it

From the repository root. `--plan` needs no key; the others need `SPREAD_URL` and `SPREAD_KEY` (add `--env-file .env`
after `uv run` to read them from `.env`). A tournament is **one online run**, like the bench: see
[`AGENTS.md`](../../AGENTS.md) and [`active-models.md`](../../active-models.md) before you start one.

```sh
uv run python -m strategies.tournament --plan      # round 1, and which of its weeks are saved: plays nothing
uv run python -m strategies.tournament             # every layer, on spread-1 to spread-3, level 8
uv run python -m strategies.tournament --layers slack_fees,war_guard,tempo --seeds spread-4..spread-8
uv run strategies/tournament/mix.py --layers slack_fees,tempo --level 8 --seed spread-1   # one week of one mix
```

| Option     | Default                     | What it does                                                                     |
| ---------- | --------------------------- | -------------------------------------------------------------------------------- |
| `--seeds`  | `spread-1..spread-3`        | The seeds every line-up plays, as the bench reads them. More seeds, more weeks.  |
| `--layers` | every layer                 | The layers that take part, comma-separated.                                      |
| `--also`   | `dispatch.py`               | Other systems that play the same seeds as they are. `--also` alone: none.        |
| `--rounds` | no limit                    | Stop after this many rounds. `--rounds 1` compares the layers and mixes nothing. |
| `--jobs`   | `6`                         | Weeks played at once, 1 to 8. Six leaves two practice slots for teammates.       |
| `--level`  | `8`                         | The practice level. The final is level 8.                                        |
| `--fresh`  | off                         | Play every week, also those with a saved week.                                   |
| `--plan`   | off                         | Print round 1 and its saved weeks, and play nothing.                             |
| `--csv`    | `out/tournament-<time>.csv` | Where to write the weeks as CSV.                                                 |

## The layers

A layer is one folder's change to the ceiling system: the class it puts in one part of the desk. Each folder's
README says what the change is and how it did alone.

| Layer              | Part it changes    | Class                                  | The change                                      |
| ------------------ | ------------------ | -------------------------------------- | ----------------------------------------------- |
| `slack_fees`       | fees               | `SlackFeePlanner`                      | The early fee held for cars with a day to wait  |
| `war_guard`        | admission, pricing | `WarGuardAdmission`, `WarGuardPricing` | The price war's lessons undone, a wider outage  |
| `tempo`            | admission          | `TempoAdmission`                       | An area's capacity by how fast our gigs book    |
| `learned_cost`     | admission          | `LearnedCostAdmission`                 | The driver cost corrected by our own bookings   |
| `trust_value`      | admission          | `TrustValueAdmission`                  | The dealer trust that an order on time buys     |
| `scarcity_ceiling` | admission          | `ChainScarcityAdmission`               | The town's scarcity priced in, no capacity gate |
| `profit_max`       | pricing            | `ProfitPricing`                        | The price with the most expected margin         |
| `option_menu`      | the quote          | `OptionMenu`                           | Admission's option and every slower one         |
| `bundling_more`    | bundling           | `WaitingBundler`                       | Every order waits for a chain                   |
| `bundling_cheaper` | bundling           | `CheapBundler`                         | A bundle keeps a smaller share of its solo fees |

The two bundling layers were built on the price ladder; here their bundlers run on the ceiling system.

## The mixed system

`mix.py` is the ceiling system with the layers named in `--layers`. Its other options are those of `dispatch.py`.
With one of the eight layers that have a system of their own, it is that system: fed a saved week offline, the mixed
desk of each decides the same actions as the layer's own `dispatch.py`. No mix has played a week on the server yet.

Two layers that change the same part become one class that inherits from both, as
[`scarcity_ceiling`](../scarcity_ceiling/README.md) combines two. Each layer's class calls the next one's method, so
every change applies: with `war_guard` and `tempo`, admission widens the area for the outage, then scales it by the
tempo, then takes the base's verdict. The classes are asked in the order of the table above. The mixed class's
thresholds are the ceiling's, with what each layer adds or sets.

`mix.py` refuses a set of layers before it creates a world when:

- two layers give one threshold different values, so one `Params` cannot hold both. `tempo` and `learned_cost` both
  have `pool` and `high`, with different values, so they cannot be mixed;
- two layers define the same new method for one part, so one would hide the other's;
- the layers add nothing together: `scarcity_ceiling` drops the capacity gate, which is all that `tempo` changes.

A mix saves its weeks with a policy of its own, such as `mix:ceiling+slack_fees+tempo`, so each line-up forms its
own group in `out/spread.sqlite`.

## The rounds

A line-up is the ceiling system with a set of layers, written `ceiling+slack_fees+tempo`. Every line-up plays every
seed, so all of them can be compared.

1. Round 1 plays `ceiling`, the champion, and each layer alone on `ceiling`. The systems of `--also` play too.
2. The best line-up that beat the champion becomes the champion. A layer whose line-up did not beat the champion is
   out, and so is one whose week failed.
3. The next round adds each layer that is still in to the new champion. A layer that cannot join it (above) is out.
4. It ends when no line-up beat the champion, or no layer is left.

One line-up beats another as teams are ranked in the practice rankings and the final: a line-up whose every week is
ranked (90% on time) comes before one with an unranked week, then the higher mean margin of a week wins.

At the end it prints the standings of every line-up it played, the champion with the command that plays it, and the
best single ranked week with its world id. The CSV has one row for each week.

## The standings

| Column         | Meaning                                                                          |
| -------------- | -------------------------------------------------------------------------------- |
| Round          | The round the line-up first played in.                                           |
| Margin a week  | The mean gross margin over the seeds: the score.                                 |
| vs ceiling     | That mean less the plain ceiling system's, on the same seeds.                    |
| Ahead          | On how many of the seeds its margin was above the ceiling system's.              |
| Ranked         | How many of its weeks count for the rankings: at least 90% on time.              |
| Lowest on time | The on-time share of its worst week. Under 90%, that week does not count at all. |
| Best week      | Its highest margin of a week.                                                    |

Round 1 of the seven layers that have a system of their own, read from their saved weeks on 2026-11-14 with
`--rounds 1 --also`, level 8, `spread-1` to `spread-3`. No week was played for it:

```text
#  Line-up               Round  Margin a week  vs ceiling   Ahead  Ranked  Lowest on time   Best week
1  ceiling+slack_fees        1      €7,058.49    +€119.47  2 of 3  3 of 3           97.5%  €10,206.83
2  ceiling+war_guard         1      €7,030.79     +€91.77  2 of 3  3 of 3           96.5%  €10,223.10
3  ceiling+tempo             1      €6,982.10     +€43.08  1 of 3  3 of 3           97.8%   €9,751.76
4  ceiling                   1      €6,939.02                      3 of 3           97.4%   €9,831.09
5  ceiling+learned_cost      1      €6,801.78    -€137.24  0 of 3  3 of 3           98.3%   €9,774.16
6  ceiling+option_menu       1      €6,530.21    -€408.81  1 of 3  3 of 3           97.8%   €8,529.94
7  ceiling+profit_max        1      €6,414.48    -€524.54  0 of 3  3 of 3           98.2%   €9,076.00
8  ceiling+trust_value       1      €5,695.69  -€1,243.33  0 of 3  3 of 3           97.3%   €8,995.51
```

No mix of two layers has been played yet: round 2 needs the server.

## Saved weeks

The same code on the same seed plays the same week, so the tournament reads a saved week from `data/scrape/runs`
instead of playing it again. It reads a week when all of these hold:

- it is a practice week of the line-up's policy, on that seed and level;
- the code that decides the line-up's week is the same now as at the commit that played it: the line-up's file and
  every module under `strategies/` and the root `dispatch.py` that it imports. A change to another system, to
  `tools/` or to a README does not count;
- the week was played from committed code. `meta.json` marks a week played with uncommitted changes as `-dirty`.

So **commit your code before a tournament**, or its weeks cannot be read later. Saved weeks of one line-up that
disagree are not trusted, and the week is played.

The root `dispatch.py` is played every time. Its weeks are saved as `dispatch`, and so are the baseline's and older
weeks of other systems, so a saved one cannot be told from theirs (#215).

Every week the tournament plays is saved like any other online run. Commit the new folders under `data/scrape/runs`
with your PR.

## Limits

- **A small lead on three seeds is noise.** `slack_fees` leads `ceiling` by under 2% and on two seeds of three. Play
  more seeds before the team picks a champion for the final: with `--seeds`, every line-up plays them all.
- The rounds are greedy: they add one layer at a time to the best line-up. A layer that only helps together with a
  second one is knocked out in round 1, and the best mix may not be on the path. `mix.py` plays any mix by itself.
- A mix has no saved week until it has played one, so a new mix costs a week on every seed.
- The layers are the systems built on `ceiling`. The ladders, `scarcity_cost` and `delivery_urgency` quote in another
  way and are not layers; they can play beside the line-ups with `--also`.

## Add a layer

1. Build the change as a subclass of the ceiling system's class for its part (`ChainAdmission`, `CeilingPricing`,
   `FeePlanner`, `Bundler`), with its thresholds in a `Params` in the same module, as the other folders do.
2. In each method it overrides, call `super()`, so the next layer's change applies too.
3. Give its thresholds and new methods names that no other layer uses.
4. Add one line to `LAYERS` in [`mix.py`](mix.py): the class for each part, and `desk=True` when its `dispatch.py`'s
   `Desk` adds a step to `handle`, `carry` or `quote`. Its place in `LAYERS` is its place in the order.
