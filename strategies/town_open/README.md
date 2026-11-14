# Town opening

A dispatch system built on [`strategies/lane_prior`](../lane_prior/README.md): its `Desk` is a subclass of the
lane-prior desk whose gigs open at a fee learned for each pickup town. Issue #200. The systems it builds on stay as
they are.

| File          | Class            | Builds on           | What it decides                                              |
| ------------- | ---------------- | ------------------- | ------------------------------------------------------------ |
| `opening.py`  | `TownOpening`    | `Strategy`          | The opening fee of each pickup town, from its bookings       |
| `opening.py`  | `TownFeePlanner` | `DawnFeePlanner`    | The dawn schedule, opened at the town's fee                  |
| `dispatch.py` | `Desk`           | the lane-prior desk | The system: tells `TownOpening` each gig it posts            |

Both classes are subclasses of `Strategy` ([`strategies/strategy.py`](../strategy.py)) with the constructor
`(roster, world_map, level=8, params=None)`; `TownOpening` has a frozen `Params`, and the desk feeds it every event.

## Run it

From the repository root:

```sh
uv run strategies/town_open/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/town_open/dispatch.py strategies/lane_prior/dispatch.py --jobs 2
```

Its weeks are saved with the policy `town-open`. The `Town opening` line at the end of a week counts the gigs that
booked quickly at their opening fee and those that needed a raise, and gives the world's opening fee and the three
cheapest and three dearest towns.

## What the saved weeks show

Every gig opens at 0.9 times its typical fee (`strategies/fees`). In the 31 saved level 8 weeks with that schedule,
58% of the one-order gigs booked at the opening fee, half of them within 6 minutes: for those cars the cheapest driver
would have come for less. For cars ready 8 to 24 hours after the post, 70% to 76% booked at the opening fee, with a
median of 7 to 9 minutes. Level 8 gives each town its own share of the drivers, new in every world, and the driver
list does not say who works, so the right opening fee differs by town and by world. At level 1, where drivers do not
learn our fees, opening at half the typical fee raised the week's margin from €21 to €6,037 (`strategies/fees`).

## The strategy

1. **One opening fee for the world, and an offset for each pickup town**, both as multiples of the typical fee.
   Every town starts at 0.9.
2. **A quick booking lowers it.** When a driver books a gig at its opening fee within 20 minutes of the post
   (`quick`), the world's fee falls 0.6% and the town's offset 1.2%.
3. **A raise lifts it.** When a gig is booked above its opening fee, or expires without a driver, the world's fee
   rises 0.9% and the town's offset 1.8%. The steps balance where 60% of a town's gigs book quickly
   (`quick_share`).
4. **A slow booking at the opening fee** moves nothing.
5. **Limits.** A town opens between 0.72 and 1.0, and its offset stays within 0.12 of the world's fee.

Only a gig of one order that opened at its town's fee teaches: a gig with little time left opens higher
(`strategies/fees`) and says nothing of the town. An accepted direct offer does not say its fee, so it teaches
nothing. The rest of the schedule is the dawn schedule of `strategies/dawn_fees`: the fee after two hours and the
dawn ladder do not move with the opening.

## The variables

`Params` in `opening.py`, exported as `TownParams`.

| Variable      | Default    | What it does                                                         |
| ------------- | ---------- | -------------------------------------------------------------------- |
| `start`       | 0.9        | Where every town opens on Monday                                     |
| `low`, `high` | 0.72, 1.0  | No town opens below or above these                                   |
| `quick`       | 20 minutes | A booking at the opening fee within this of the post is a quick one  |
| `quick_share` | 0.6        | The share of quick bookings that the opening settles at              |
| `step`        | 0.015      | The world's step per gig, times (raised − (1 − `quick_share`))       |
| `town_step`   | 0.03       | The same for the town's offset                                       |
| `town_limit`  | 0.12       | A town's offset stays within this of the world's opening             |
