# Snow-aware planning

A dispatch system built on [`strategies/headroom`](../headroom/README.md). It changes two decisions from level 5,
where `forecast` events announce snow. Admission and pricing, the root desk and the other headroom strategies stay as
they are. The note reader still handles summer tyres: a car that cannot be collected in snow waits for a clear window
at either end.

| File          | Class         | Builds on         | What it decides                                        |
| ------------- | ------------- | ----------------- | ------------------------------------------------------ |
| `snow.py`     | `SnowState`   |                   | The forecast snow windows at each place                |
| `snow.py`     | `SnowPlanner` | `LaneFeePlanner`  | The opening fee when snow is forecast on pickup day    |
| `snow.py`     | `SnowBundler` | `Bundler`         | Snow-local chain timing and the wait before posting    |
| `dispatch.py` | `Desk`        | the headroom desk | The system, with one state shared by fees and bundling |

## Shared state and cold start

The desk makes one `SnowState` and passes it to both strategies. Each `observe` adds every `(from, to)` window to a
set for every `placeId` in a `forecast`; repeats and the two observers do not duplicate it. The state answers whether
snow overlaps a drive and whether any snow is forecast at the pickup place on its pickup day. Later forecasts update
the decisions made afterwards; they do not reprice an existing gig or reopen an already checked chain.

Before the first forecast, the state is empty. `SnowPlanner` calls the headroom planner and `SnowBundler` calls the
base `due`, so a week without forecasts is exactly the headroom system. When the desk rejoins a week, event history
rebuilds the same state. There is no weather estimate from saved weeks, and no attempt to replace the note reader's
summer-tyre handling.

## Which legs slow down

The base bundler stretches every drive to 1.15 times its road minutes (`slow`). Here a positive-length leg instead
uses `snow_slow` only when either its start or end place has forecast snow overlapping the interval from departure to
its fair-weather arrival. The first stop has no incoming drive. The map exposes no intermediate route places, so only
the two ends can be checked. A leg with no such overlap keeps 1.15, even in a chain whose other legs meet snow.

The 12-hour rule, `max_drive` and the saving calculation still use road minutes. Opening hours, stop windows, the
pickup wait and the chain-growth rule are the base's. If any leg meets snow, every delivery in that chain must arrive
`buffer + snow_buffer` before its window ends: with the defaults, two hours instead of one. Otherwise the delivery
buffer stays at the base hour, so a fair-weather chain keeps the same candidate thresholds and order of growth.

## Opening fee and earlier posting

`SnowPlanner` uses the pickup of the first undelivered car and the later of now and its stated window start. If snow
is forecast anywhere at that place on that calendar day, `snow_premium` is added to both the dawn plan's `open` and
the sprint plan's `sprint_open`. With the defaults these open at 1.10 and 1.30 times the lane fee instead of 0.90 and
1.10. The later of the stated window and now makes a delayed pickup use its own day, not the posting day.

Only the opening changes. The usual top, price-worth and late-car ceilings still clamp the schedule, the rest of the
ladder keeps its shape, and the fee after a drop keeps the headroom rule. A forecast on another day or only at the
delivery place does not add this premium.

A `SnowBundler` remembers each won or changed order's first pickup. The same day test lets that order skip the
remaining batch hold, so the root desk can post it at its next `post_due` instead of waiting for the batch to go
quiet. It does not create an extra posting action outside the desk's loop. Other orders retain the base hold and quiet
rules.

## Frozen parameters

`Params` extends the frozen `DawnParams`; `BundlerParams` extends the frozen bundling `Params`. All inherited values
stay at their headroom/base defaults.

| Variable       | Default | What it does                                                      |
| -------------- | ------- | ----------------------------------------------------------------- |
| `snow_premium` | 0.20    | Added to the opening multiple on a snowy pickup day               |
| `snow_slow`    | 1.35    | Drive stretch on a forecast-affected leg, against the base's 1.15 |
| `snow_buffer`  | 60 min  | Extra delivery buffer for a chain with any forecast-affected leg  |

## Run it

From the repository root:

```sh
uv run strategies/snow_aware/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `snow-aware`.
