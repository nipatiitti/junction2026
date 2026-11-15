# Bulk-yard handling

A dispatch system built on [`strategies/headroom`](../headroom/README.md). It treats a dealer group's large batch as
one capacity problem, then keeps its won orders together for yard-first chains. Headroom and the root system stay as
they are. Issue #249.

| File           | Class               | Builds on           | What it decides                                               |
| -------------- | ------------------- | ------------------- | ------------------------------------------------------------- |
| `admission.py` | `BulkYardAdmission` | `LaneCostAdmission` | How many requests of a large batch to quote, and the discount |
| `bundling.py`  | `BulkYardBundler`   | `Bundler`           | Which cars of a large batch share a yard-first chain          |
| `dispatch.py`  | `Desk`              | the headroom desk   | Joint batch quoting, with the two strategies above            |

Both strategies have frozen `Params` dataclasses. The defaults are conservative placeholders, not tuned values; no
online weeks or benchmarks were run for this change.

## Run it

From the repository root:

```sh
uv run strategies/bulk_yard/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `bulk-yard`.

## One capacity estimate per batch

A batch is the requests that share a `batchId`; its size is the number seen so far. Admission assumes the batch's
requests start at one yard and arrive in one go. Below `bulk_min` (10 requests), every decision and price is
headroom's. When the batch reaches that size, the desk requotes every request that is still open, so the earlier
small-batch quotes are replaced before their `respondBy`. Later requests join the same plan and another still-open
batch quote replaces the previous one.

For the capacity estimate, requests go in earliest-option-deadline order. Only drivers whose homes are at most
`bulk_near` (90 road minutes) from the yard count. A premium car can use only an experienced driver (rating at least
4.8 and at least 50 completed gigs). Each request is put on the eligible driver who can finish it first:

- the first drive starts at that driver's road time from home to the yard;
- each car's work waits until its stated pickup window and takes the request's road minutes, multiplied by
  `bulk_slow` (1.15);
- delivery must be `bulk_buffer` (60 minutes) before the earliest offered deadline;
- after a delivery, the driver takes the road trip back to the yard before their next car.

The estimate accepts only the requests that fit this greedy schedule. Headroom's ordinary area gate is replaced for
those requests by this batch budget: otherwise its two-car minimum would stop the joint plan before the yard schedule
mattered. The option slack, lead cost, timed return-leg checks and note-deadline check still apply. Requests that do
not fit the yard schedule are declined with the usual deliberately losing quote.

This is a capacity estimate, not a reservation. It uses the roster, not who works that day, their existing jobs,
opening hours, notes beyond headroom's checks, or our other orders. **The yard's drivers may never show up**: they may
be ill, off duty, take other work or decline our fees, so the estimate can still accept cars nobody collects. A remote
yard can have the opposite risk: too few requests accepted even though a slightly higher fee would attract a driver.

## The discount and accept-up-to rule

Requests in the yard schedule are quoted at headroom's normal learned price with `bulk_discount` (0.05) applied to the
list prices. Admission includes that discount in its profit check, and pricing keeps its usual driver cost plus risk
premium as a floor. Thus the discount becomes smaller at that floor and an option is declined if the discounted ceiling
cannot cover the floor. At most the number admitted by the yard schedule can receive normal discounted quotes;
headroom may accept fewer for its usual time or margin reasons. There is no attempt to win the rest of the batch.

## Yard-first chains

`BulkYardBundler` uses the base batch timing unchanged: a won order waits at most `hold` (45 minutes), never later than
`safe` (6 hours before its last pickup), and may go when its batch has no open request and has been quiet for `quiet`
(20 minutes). A large batch's waiting orders are not borrowed by unrelated chains. When its base hold/quiet rule lets
the batch go, all its won orders are candidates in one separate call to the base chain planner, starting from their
common pickup yard. Below `bulk_min`, orders use the base's shared pool exactly as before.

The base planner still requires a positive driver-minute saving and enforces `max_cars`, `max_drive`, the 12-hour rule,
all stop windows and opening hours, audience equality and the usual bundle fee scaling. One driver can therefore take
several cars out of the yard when a return to it saves trips; this system does not force a bundle when those checks do
not find a saving. Bundles that expire, fail, split at a deadline warning or change plan are handled by the unchanged
headroom desk.
