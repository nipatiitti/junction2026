# Facts: derived analysis tables

## What it is

Derived tables in the scrape database, so that a question about the world is one SQL query. They are built from
the raw tables of `db.py` (see the main README) and live in the same file, beside the `probes`,
`fee_probes` and `shape_probes` tables of `db.py` that hold the probe rows:

```sh
uv run python -m analysis.facts                          # build the weeks that have no facts yet (out/spread.sqlite)
uv run python -m analysis.facts --db data/spread.sqlite  # another database
uv run python -m analysis.facts --rebuild                # drop the facts tables and build every week
uv run python -m analysis.facts --week 71 --week 72      # rebuild only these weeks (weeks.id)
```

It builds only the weeks that are new, each in one transaction, so it is safe to rerun at any time, also while a
scrape writes to the database. A played week takes about 0.1–0.3 s, the 133,000-event starter week about 1.5 s.
When the definitions change, `VERSION` in `facts.py` goes up and the next run rebuilds every week.

Conventions: `day = at // 1440` (0 Monday … 4 Friday, 7 last Monday, 9 last Wednesday), `hour = at % 1440 // 60`.
Money is in integer cents. Ratios are not rounded. Flags are 0/1. A value that cannot be known is null, never 0.
"Near" means within 30 km in a straight line (the notification radius). An experienced driver has a rating of at
least 4.8 and at least 50 completed gigs.

## The tables

### `week_facts`: one row per week

| Column                                                                       | Meaning                                                                                                           |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `week_id`, `world_id`, `seed`, `level`, `policy`                             | from `weeks`                                                                                                      |
| `experiment`                                                                 | the folder after `scrape/` (`passive`, `explore-win`, `explore-ceiling`, `starter`…), else the policy             |
| `recorded`                                                                   | 1 when the week has an action log (`actions` rows)                                                                |
| `quote_share`, `fee_shape`, `fee_cap`, `offers`                              | the explore settings (`weeks.settings`)                                                                           |
| `quote_lo`, `quote_hi`, `fee_lo`, `fee_hi`                                   | the explore ranges                                                                                                |
| `drivers`, `drivers_experienced`, `drivers_manual`, `towns_with_drivers`     | the driver list at the start                                                                                      |
| `requests`, `quoted`, `declined`, `unquoted`                                 | requests; with a real quote; only declined (≥ 5 × list); never answered                                           |
| `won`, `cancelled`, `counted`, `delivered`, `on_time`, `late`, `undelivered` | orders, from `order_facts`                                                                                        |
| `on_time_share`                                                              | `on_time / counted` (equals `weeks.on_time_share`)                                                                |
| `late_slack`                                                                 | `counted // 10 - (late + undelivered)`: more late orders the week can take and stay at 90%; negative = not ranked |
| `revenue_cents` … `fine_cents`, `other_cents`                                | ledger sums by kind, signed as in the ledger (costs negative)                                                     |
| `margin_cents`                                                               | sum of every ledger line (equals `weeks.margin_cents`)                                                            |
| `gigs`, `bookings`, `drops`, `no_shows`, `expired`, `views`                  | gigs; `gig_booked`, `gig_dropped`, `no_show`, `gig_expired` events; views                                         |
| `war_day`                                                                    | the day `week_days` guesses as the price war, else null                                                           |
| `facts_version`                                                              | the builder's `VERSION`                                                                                           |

### `quote_facts`: one row per delivery option of each request (the win model)

| Column                                                                                          | Meaning                                                                                                                 |
| ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `week_id`, `level`, `request_id`, `option`                                                      | the option (`same_day`, `next_day`, `within_3_days`)                                                                    |
| `dealer_id`, `batch_id`, `batch_size`                                                           | the dealer; requests in the same batch (1 without one)                                                                  |
| `arrived_at`, `respond_by`, `day`, `hour`                                                       | when the request came; `day`, `hour` of `arrived_at`                                                                    |
| `legs`                                                                                          | cars of the request (2 = trade-in)                                                                                      |
| `pickup_place`, `delivery_place`, `km`                                                          | leg 0                                                                                                                   |
| `km_total`, `minutes_total`                                                                     | over all legs                                                                                                           |
| `private_pickup`, `private_delivery`, `premium`, `electric`                                     | true on any leg                                                                                                         |
| `low_charge`                                                                                    | an electric car under 30% going over 200 km (needs a charging stop)                                                     |
| `has_note`, `note_language`                                                                     | the request has a note; its language                                                                                    |
| `options_offered`, `option_rank`                                                                | options of the request; 0 same day, 1 next day, 2 within three days                                                     |
| `deadline`, `hours_to_deadline`                                                                 | the option's deadline; hours from arrival to it                                                                         |
| `lead_minutes`                                                                                  | leg 0 ready time minus arrival                                                                                          |
| `list_price_cents`, `reference_fee_cents`, `fee_share`                                          | list price; typical driver fee of the request; their ratio                                                              |
| `quote_cents`, `ratio`                                                                          | our last quote (null when not priced); quote over list                                                                  |
| `declined`, `quoted`                                                                            | `ratio >= 5` (a decline); a real quote                                                                                  |
| `options_quoted`, `cheapest`, `min_other_ratio`                                                 | quoted options of the request; this is the cheapest; the lowest ratio among the others                                  |
| `outcome`, `taken`                                                                              | `won`, `lost`, `unquoted`; the dealer took this option from us                                                          |
| `dealer_trust`                                                                                  | the dealer's trust count at the decision, rebuilt from revenue and refund lines (+1 on time up to 25, halved when late) |
| `dealer_on_time_before`, `dealer_late_before`                                                   | our orders for this dealer delivered on time / late before the decision                                                 |
| `dealer_open_orders`, `dealer_overdue_open`                                                     | its orders won and not delivered; those past their deadline                                                             |
| `dealer_requests_before`, `dealer_quoted_before`, `dealer_won_before`, `dealer_unquoted_before` | the dealer's earlier decided requests of the week                                                                       |
| `drivers_pickup`, `drivers_delivery`, `drivers_near_pickup`, `drivers_near_delivery`            | drivers living at / near leg 0's places                                                                                 |
| `war_guess`                                                                                     | the request came on the guessed price-war day                                                                           |

### `order_facts`: one row per won order (cancelled included)

| Column                                                                                                                              | Meaning                                                                                    |
| ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `week_id`, `level`, `order_id`, `dealer_id`, `option`                                                                               |                                                                                            |
| `won_at`, `day`, `hour`                                                                                                             | when we won it                                                                             |
| `legs`, `pickup_place`, `delivery_place`, `km`, `km_total`, `private_pickup`, `private_delivery`, `premium`, `electric`, `has_note` | the request's lane and cars                                                                |
| `price_cents`, `list_price_cents`, `ratio`, `reference_fee_cents`                                                                   | our price; the taken option's list price; their ratio; typical fee                         |
| `deadline_won`, `last_pickup_won`, `deadline`                                                                                       | deadline and last pickup at the win; the deadline at the end                               |
| `changes`, `place_changed`                                                                                                          | changes of plan; one of them moved a place                                                 |
| `ready_late`, `held`, `needs_plates`, `manual_gearbox`, `summer_tyres`, `note_deadline`, `hours_differ`                             | the truth behind the note (reveal)                                                         |
| `status`, `cancelled`, `cancelled_at`, `counted`                                                                                    | status at the end; cancelled; when; counts for the delivery minimum                        |
| `delivered_at`                                                                                                                      | minute of its revenue line                                                                 |
| `revenue_cents` … `other_cents`                                                                                                     | its ledger lines by kind, signed                                                           |
| `extra_driving_cents`                                                                                                               | the part of `driver_fee_cents` paid for extra driving after a change of plan               |
| `margin_cents`                                                                                                                      | sum of the account columns                                                                 |
| `refund_pct`, `late_minutes`                                                                                                        | from the late refund line; `late_minutes` is 0 when on time                                |
| `late_bucket`                                                                                                                       | `on_time`, `le_2h`, `le_24h`, `le_2bd`, `gt_2bd`, `late_other`, `undelivered`, `cancelled` |
| `on_time`                                                                                                                           | null when cancelled                                                                        |
| `gigs`, `bookings`, `drops`, `no_shows`, `expired`, `reprices`, `failed_visits`, `views`, `viewers`                                 | over the gigs that carry it                                                                |
| `shared_gig`                                                                                                                        | a gig of it also carries another order                                                     |
| `first_posted_at`, `minutes_to_post`, `first_fee_ratio`                                                                             | its first gig; minutes from the win; its opening fee over the typical fee                  |
| `first_view_fee_cents`                                                                                                              | the fee a driver saw first (what drivers learn from)                                       |
| `first_booked_at`, `minutes_to_booking`, `first_booked_ratio`                                                                       | the first booking; minutes from the first post; fee over typical                           |
| `paid_ratio`                                                                                                                        | driver fees paid (without extra driving) over the typical fee                              |
| `open_minutes`                                                                                                                      | minutes its gigs were open                                                                 |
| `dealer_trust_won`                                                                                                                  | the dealer's trust count when we won it                                                    |

### `gig_facts`: one row per gig (fee bound, how low drivers go, where bookers live)

| Column                                                                                                           | Meaning                                                                                                     |
| ---------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `week_id`, `level`, `gig_id`, `source`                                                                           | `source`: `actions` (fees rebuilt from the action log) or `gigs` (last schedule only)                       |
| `order_id`, `orders`, `cars`, `order_post_no`                                                                    | first stop's order; orders and cars in it; 1 for the order's first gig, 2 for the next…                     |
| `pickup_place`, `delivery_place`, `km`, `drive_minutes`                                                          | first pickup, last delivery, over its cars                                                                  |
| `private_pickup`, `private_delivery`, `premium`, `experienced`, `manual_licence`, `with_plates`, `with_charging` | its cars and audience                                                                                       |
| `posted_at`, `posted_day`, `posted_hour`                                                                         |                                                                                                             |
| `typical_fee_cents`                                                                                              | the typical fee for its cars                                                                                |
| `opening_fee_cents`, `opening_ratio`, `top_fee_cents`                                                            | first step of the first schedule; over typical; last step of the last schedule                              |
| `steps`, `reprices`                                                                                              | steps of the first schedule; reprices                                                                       |
| `spells`, `open_minutes`                                                                                         | its `gig_spells` rows; minutes open                                                                         |
| `views`, `viewers`, `bookings`, `drops`, `no_shows`, `failed_visits`                                             |                                                                                                             |
| `first_booked_at`, `first_booked_fee_cents`, `minutes_to_booking`                                                | the first booking                                                                                           |
| `outcome`                                                                                                        | `open`, `booked`, `working`, `done`, or for a withdrawn gig `expired`, `cancelled`, `released`, `withdrawn` |
| `driver_id`, `booked_at`, `fee_cents`, `fee_ratio`                                                               | the last booking (null without a driver)                                                                    |
| `paid_cents`, `started_at`                                                                                       | driver fees paid (positive); last start                                                                     |
| `last_pickup_at_post`, `minutes_to_last_pickup`                                                                  | the order's last pickup known at the post; minutes left                                                     |
| `driver_home`, `home_to_pickup_km`, `delivery_to_home_km`                                                        | where the driver lives; road km to the pickup and back home                                                 |

### `gig_spells`: one row per period a gig was open at one fee within one day (the booking hazard)

| Column                                                                                                                                                               | Meaning                                                                                        |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `week_id`, `level`, `gig_id`, `spell`, `source`                                                                                                                      | `spell` numbers the gig's rows in time order                                                   |
| `fee_run`                                                                                                                                                            | rows with one `fee_run` are one period at one fee, cut at midnight                             |
| `interval`                                                                                                                                                           | open intervals of the gig: a new one after each drop or no-show                                |
| `order_id`, `order_post_no`, `cars`, `orders`, `pickup_place`, `delivery_place`, `km`, `drive_minutes`, `private_pickup`, `premium`, `experienced`, `manual_licence` | of the gig                                                                                     |
| `start_at`, `end_at`, `minutes`, `day_minutes`                                                                                                                       | the period; its minutes; those between 07:00 and 23:00                                         |
| `day`, `hour`                                                                                                                                                        | of `start_at`                                                                                  |
| `fee_cents`, `typical_fee_cents`, `fee_ratio`, `next_fee_cents`                                                                                                      | the fee shown; typical; ratio; the next row's fee after a raise, reprice or midnight           |
| `last_pickup_at`, `minutes_to_last_pickup`, `deadline_warned`                                                                                                        | the order's last pickup known at `start_at`; minutes left; a `deadline_close` came             |
| `opened_by`                                                                                                                                                          | `post`, `drop`, `no_show`                                                                      |
| `order_age_minutes`                                                                                                                                                  | minutes since the order's first gig was posted                                                 |
| `views`, `viewers`, `new_viewers`                                                                                                                                    | views in the row; drivers; drivers who had not seen the order before                           |
| `order_views_before`, `order_viewers_before`, `order_viewed_before`                                                                                                  | views of the order's gigs before `start_at`                                                    |
| `first_view_fee_cents`, `fee_over_first_view`                                                                                                                        | the order's first viewed fee (before `start_at`); this fee over it                             |
| `order_bookings_before`                                                                                                                                              | earlier bookings of the order's gigs                                                           |
| `taught_orders`, `taught_raise`, `taught_wait`                                                                                                                       | the week's bookings so far; their mean fee over the first viewed fee and mean minutes after it |
| `drivers_pickup`, `drivers_near_pickup`, `snow`                                                                                                                      | drivers at / near the pickup; snow forecast there                                              |
| `offers`                                                                                                                                                             | direct offers sent during the row                                                              |
| `end_kind`                                                                                                                                                           | `booked`, `raise`, `reprice`, `midnight`, `expired`, `withdrawn`, `cancelled`, `end`           |
| `end_estimated`                                                                                                                                                      | the end is a guess (a withdraw without the action log)                                         |
| `booked`, `driver_id`, `booked_fee_cents`, `via_offer`                                                                                                               | the booking that ended the row                                                                 |
| `kept`                                                                                                                                                               | the booking held to the end (no drop, no-show, release or cancellation)                        |
| `view_fee_mismatches`                                                                                                                                                | views in the row that saw another fee                                                          |

### `town_days`: one row per week, place and day 0–9 (supply)

| Column                                                                         | Meaning                                                                      |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| `week_id`, `level`, `place`, `day`                                             |                                                                              |
| `drivers_home`, `experienced_home`, `manual_home`, `drivers_near`              | drivers living there / near                                                  |
| `snow`                                                                         | a forecast covers the place that day                                         |
| `requests`, `requests_delivery`, `won`                                         | requests that day picking up / delivering there; orders won picking up there |
| `viewers_home`, `views_home`, `bookers_home`, `bookings_home`, `starters_home` | drivers living there who viewed, booked, started a gig that day              |
| `gigs_posted`, `gigs_open`, `open_minutes`                                     | gigs picking up there: posted; open; minutes open                            |
| `views`, `viewers`, `bookings`, `booked_share`                                 | views and bookings of those gigs; bookings per open gig                      |
| `mean_booked_ratio`, `min_booked_ratio`                                        | booked fee over typical fee                                                  |

Passive weeks fill only the drivers, snow and requests columns.

### `week_days`: one row per week and weekday 0–4 (day effects, the price war)

| Column                             | Meaning                                                                            |
| ---------------------------------- | ---------------------------------------------------------------------------------- |
| `week_id`, `level`, `day`          |                                                                                    |
| `requests`, `quoted`, `won`        | requests arriving that day; quoted; won                                            |
| `band_n`, `band_won`, `band_share` | real quotes at 1.0–1.25 × list between 08:00 and 18:00; those taken; their share   |
| `war_score`                        | `band_share` minus the mean of the week's other days (with 10+ quotes in the band) |
| `war_guess`                        | the day with the lowest score, at level 8, when it is −0.25 or lower               |

## Reading the data

- Fit the win model on `quote_facts.quoted = 1`. Declines (10 × list) and unpriced options are in the table too.
- `taken` is per option: 0 means the dealer did not take this option from us (it may have taken another one).
- Money in `order_facts` and `week_facts` is signed as in the ledger, so a margin is a plain sum.
- Lateness comes from the ledger (refund lines), not from `orders.late_minutes`, which misses note deadlines
  and booked hours.
- Spells with `source = 'gigs'` (weeks without an action log, such as the starter week in `data/spread.sqlite`)
  know only the last fee schedule, so fees before a reprice are wrong: filter `source = 'actions'` or
  `view_fee_mismatches = 0`.
- `dealer_trust` is rebuilt from revenue and refund lines. The rules give it an effect only at level 8.
- `war_guess` is a guess: in about half of the explore weeks no day stands out, and Monday reads low because trust
  starts at zero.
- Lanes are the request's places; a change of plan can move a place (`order_facts.place_changed`).
- The `offers` and `via_offer` columns follow the rules; no scraped week has direct offers yet.

## Example queries

Each answers a question of the brief.

```sql
-- 1. Win curve (win_prob): does the win share fall with the price? Level 8.
select round(ratio, 1) r, count(*) n, round(avg(taken), 3) win
from quote_facts where quoted = 1 and level = 8 group by 1 order by 1;

-- 2. Dealer trust: win share by price and trust count.
select round(ratio * 5) / 5 r, min(dealer_trust, 12) / 4 * 4 trust, count(*) n, round(avg(taken), 2) win
from quote_facts where quoted = 1 and level = 8 and options_quoted = 1 group by 1, 2 order by 1, 2;

-- 3. Price war and day effects: the share of mid-priced quotes that win, by day.
select w.experiment, d.week_id, d.day, d.band_n, round(d.band_share, 2) share, round(d.war_score, 2) score, d.war_guess
from week_days d join week_facts w using (week_id) where d.level = 8 and w.quoted > 0 order by 2, 3;

-- 4. Dealer ceiling / outage: where do very high quotes still win (no competitor)?
select week_id, day, pickup_place, count(*) n, sum(taken) won, round(max(case when taken = 1 then ratio end), 2) top
from quote_facts where quoted = 1 and ratio >= 1.8 group by 1, 2, 3 having won >= 3 order by won desc;

-- 5. Option choice: with several options priced, does the dealer take the cheapest or the fastest?
select option, cheapest, count(*) n, round(avg(taken), 3) taken
from quote_facts where quoted = 1 and options_quoted > 1 and outcome = 'won' group by 1, 2;

-- 6. Booking hazard (accept_hazard): bookings per open daytime hour, by fee over the typical fee.
select round(fee_ratio * 4) / 4 fee, count(*) spells, sum(booked) booked,
       round(60.0 * sum(booked) / max(sum(day_minutes), 1), 3) per_hour
from gig_spells where source = 'actions' and level = 8 group by 1 order by 1;

-- 7. Do drivers learn to wait? Hazard of a fresh order against one that drivers saw before, at the same fee.
select order_viewed_before, round(fee_ratio * 2) / 2 fee, sum(booked) booked,
       round(60.0 * sum(booked) / max(sum(day_minutes), 1), 3) per_hour
from gig_spells where source = 'actions' group by 1, 2 order by 2, 1;

-- 8. How low do drivers go, and how early? Booked fee over the typical fee by lead time.
select minutes_to_last_pickup / 720 * 12 hours_ahead, count(*) n,
       round(min(fee_ratio), 2) lowest, round(avg(fee_ratio), 2) mean
from gig_spells where booked = 1 and kept = 1 group by 1 order by 1;

-- 9. Supply (supply(region, day)): which towns book, against the drivers who live near.
select place, day, sum(drivers_near) near, sum(gigs_open) gigs, sum(bookings) booked,
       round(1.0 * sum(bookings) / max(sum(gigs_open), 1), 2) share
from town_days where level = 8 and day < 5 group by 1, 2 having gigs >= 20 order by share;

-- 10. Where the margin goes: the waterfall by experiment, and the cost of each lateness bucket.
select experiment, level, count(*) weeks, sum(revenue_cents) / 100 revenue, sum(driver_fee_cents) / 100 fees,
       sum(late_refund_cents) / 100 refunds, sum(undelivered_penalty_cents) / 100 penalties,
       sum(failed_visit_cents + waiting_cents + release_fee_cents + fine_cents) / 100 other,
       sum(margin_cents) / 100 margin, min(late_slack) worst_slack
from week_facts where won > 0 group by 1, 2;
select late_bucket, count(*) orders, sum(late_refund_cents + undelivered_penalty_cents) / 100 cost,
       round(avg(margin_cents) / 100.0, 2) mean_margin
from order_facts group by 1;
```

Several weeks share a probe's seed and level, so each flip joins every played week of that world; the list price is
in the join because the oracle treats a different list price as a different request.

```sql
-- 11. Did our quote sit under the probe's flip, and did it win? Level 8, single-option quotes.
select q.outcome, count(*) as quotes, sum(q.quote_cents <= p.bracket_low_cents) as under_flip,
       round(avg(q.ratio), 2) as our_ratio, round(avg(p.flip_ratio), 2) as flip_ratio
from probes p
join weeks w on w.seed = p.seed and w.level = p.level
join quote_facts q on q.week_id = w.id and q.request_id = p.request_id and q.option = p.option
                  and q.list_price_cents = p.list_price_cents
where p.level = 8 and p.flip_ratio is not null and p.monotone = 1 and q.quoted = 1 and q.options_quoted = 1
group by 1;
```

`shape_probes` has one row per pair that `probe.py shape` probed: each car's single flip (`single0_flip_cents`,
`single1_flip_cents`), the flip of both cars as one gig (`combined_flip_cents`), and `saving_ratio` = (sum of the
single flips − combined flip) / the pair's typical fee.

```sql
-- 12. How much does one combined gig save, by pair kind?
select kind, count(*) as pairs, round(avg(saving_ratio), 3) as mean_saving_ratio,
       round(avg(combined_over_sum), 3) as combined_over_sum, sum(same_driver) as same_driver
from shape_probes where error is null and monotone = 1
group by kind;
```

## For the hindsight oracle (#66)

The oracle reads these tables: see [Hindsight oracle](#hindsight-oracle) below.

# Hindsight oracle

## What it answers

Where each played week's margin went (the account, line by line), and how much a dispatcher with perfect hindsight
could have kept: a ladder of nested upper bounds, split into the brief's buckets (quoting, driver fees, combining).

```sh
uv run python -m analysis.oracle                                  # every played week of out/spread.sqlite
uv run python -m analysis.oracle --weeks --experiment explore-win # the week table first, one experiment
uv run python -m analysis.oracle --db data/spread.sqlite --probe out/probe --json out/oracle.json --week 73
```

It reads the facts tables, so run `uv run python -m analysis.facts` first; it opens the database read-only and never
writes to it. Weeks in scope are those with an order (`week_facts.won > 0`). `--week` and `--experiment` (repeatable)
narrow the printed tables only: the JSON (`--json`, default `out/oracle.json`, `-` for none) always holds every
played week, and the pooled inputs (fee comparables, win curves) always use every week of the database. `--probe`
is the folder of `probe.py` quote files (`quote-L<level>-<seed>.jsonl`, default `out/probe`); without one the quote
side uses brackets only. 70 weeks take about 2 s.

## The ladder

Each bound takes the one before and relaxes one more thing, so the gains add up without counting anything twice:

```
margin (actual)
  + selection_gain   perfect accept/decline, everything else as it happened
  + delivery_gain    every kept order on time, at the fees paid
  + fee_gain         every done gig at the lowest comparable fee
  + quote_gain       every request priced at its flip (sampled or estimated)
  = oracle
```

Every bound is an **upper bound on margin under its assumptions**, never a forecast. Money is integer cents, signed
as in the ledger for the account lines; every gain is ≥ 0. Ledger lines that name no order (`unallocated_cents`, 0
today) are carried unchanged through every bound.

**Selection.** Decline every order that lost money (and every cancelled one); keep the rest as they happened.
Assumes costs are those that happened, declining costs nothing (a losing quote is free), dealer trust and the
competitor's answer to fewer wins are ignored, and the drivers freed by dropped orders are not reused. It is an
upper bound for the selection alone because it keeps exactly the orders that made money. `on_time_share_after` is
the on-time share of the kept orders.

**Delivery.** Every kept order arrives on time: no refund, penalty, fine, failed visit, waiting or release fee; the
driver fees are those we paid. An order that was never delivered is costed at the week's paid fee ratio
(`cost_ratio_paid`, counted in `undelivered_costed`). Assumes a driver was there in time for every kept order at the
fee finally paid, and notes read perfectly; every removed line is a cost, so it can only raise the margin.
`refunds_avoided_cents`, `penalties_avoided_cents` and `handling_avoided_cents` split the gain for the reader but
need not add up to it: some orders become worth keeping only now.

**Fee.** Each gig a driver completed is paid the lowest fee, as a share of the typical fee, that a driver completed
a comparable gig for in the same world (same seed and level): the same car in any of our weeks (`twin`), or the same
lane booked the same day for the same audience (`lane`). Assumes the driver who took the comparable could have taken
this gig too, at that share, whatever the hour, deadline option and what drivers had learned by then. It is the
lowest of several draws, so it flatters. Coverage is honest: a gig without a cheaper comparable saves nothing.
Dropped bookings are not comparables (a driver who gives a gig back takes it again only for more).

**Quote, from probe flips** (`quote.source = "probe"`, when the week's seed and level have a probe of at least 20
requests). A probed request's flip `F` is the highest price known to win. The probe's parent world delivers nothing
and wins nothing, so a flip is the **world's first answer**: dealer trust 0, no late history, a competitor that has
not yet answered our wins. In a played week a dealer with trust `t` accepts prices up to `t`% higher (level 8), so
flips understate what on-time delivery earns later in the week; and the competitor lowers its prices for dealers
whose requests we mostly win, so they overstate what winning everything earns. The oracle adds neither: `F` is used
as it is, an order won above `F` counts 0, and `won_above_flip` shows how often trust mattered. Because the parent
wins nothing, the competitor raises its prices each morning: flips after Monday read high. The window's days are in
`days`, and the week figure extrapolates the window (`extrapolated`). Capacity is ignored: winning every profitable
request in a shortage needs drivers who are not there, and `new_cost` is the week's average paid fee ratio, not the
fee of the marginal driver. This is the loosest of the bounds. An order the selection bound dropped is still
repriced to `F` in full, which can only overstate.

**Quote, from brackets** (every week; `quote.source = "brackets"` without a usable probe). A lost quote says the
flip was below it, a won quote that it was at or above. `lost_ceiling_cents` is a strict ceiling on the revenue of
the lost requests; `lost_below_similar` counts lost requests quoted below the median winning ratio of that day, a
measure of how uneven the market is, not money. `estimate` is the expected flip given the bracket, from a win curve
(`win_curves` in the JSON) that pools all our weeks of that level and weekday (one priced option only). It knows
neither this world's price level nor the war or outage day, and it contains the trust our own weeks built by that
weekday: an **estimate**, not a bound. On the probed requests it gives 0.87–1.18 × the probe's flip revenue.

## What is measurable now (`split`)

| Bucket              | Value                         | Measurable now?                                                                                                    |
| ------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `quoting_cents`     | `selection_gain + quote_gain` | Yes. Selection exactly (given what happened); the price side exactly on probed requests, estimated elsewhere.      |
| `driver_fees_cents` | `fee_gain`                    | Partly: only against fees that some driver really took in the same world; lanes we posted once have no comparable. |
| `delivery_cents`    | `delivery_gain`               | Yes, exactly (a fourth bucket the brief does not name: lateness, penalties, handling).                             |
| `combining_cents`   | `null`                        | **No.** No scraped week has a gig with cars of two orders, so no fee of a combined gig was ever observed.          |

`combining.candidates` is the pool of counted single-leg orders that share pickup, delivery and deadline day with
another order of the week (`candidate_fee_cents`: their fees). It is the size of the pool, not a saving.

## On-time slack

`on_time.late_slack` is how many more late orders the week could have afforded and stay at 90% on time; positive
slack is unused room for risky profitable orders. With negative slack the week is not ranked and its margin does
not count at all; `drops_to_rank` is how many late orders it had to decline to be ranked. Every set the bounds keep
is fully on time, so the oracle week is ranked.

## The JSON (`out/oracle.json`)

Top-level keys: `version`, `generated_at`, `db`, `assumptions` (the text of each bound's assumptions), `weeks`,
`experiments`, `win_curves` (`level`, `day`, `rows`, `pooled`, bin midpoints `mid`, non-increasing win share `win`).
One `WEEK` (money in integer cents; `quote.probe` is null without a probe, `brackets.estimate` null without a curve):

```json
{
  "week_id": 73,
  "world_id": "w407f…",
  "seed": "scrape-1",
  "level": 8,
  "experiment": "explore-win",
  "waterfall": {
    "revenue_cents": 0,
    "driver_fee_cents": 0,
    "late_refund_cents": 0,
    "undelivered_penalty_cents": 0,
    "fine_cents": 0,
    "failed_visit_cents": 0,
    "waiting_cents": 0,
    "release_fee_cents": 0,
    "other_cents": 0,
    "margin_cents": 0,
    "unallocated_cents": 0,
    "refunds": { "le_2h": { "orders": 0, "cents": 0 }, "le_24h": {}, "le_2bd": {}, "gt_2bd": {}, "late_other": {} }
  },
  "selection": {
    "margin_cents": 0,
    "gain_cents": 0,
    "orders_kept": 0,
    "orders_dropped": 0,
    "cancelled_dropped": 0,
    "dropped_margin_cents": 0,
    "on_time_share_after": 0.97,
    "ranked_after": true
  },
  "delivery": {
    "margin_cents": 0,
    "gain_cents": 0,
    "orders_kept": 0,
    "cost_ratio_paid": 1.21,
    "undelivered_costed": 0,
    "refunds_avoided_cents": 0,
    "penalties_avoided_cents": 0,
    "handling_avoided_cents": 0
  },
  "fee": {
    "margin_cents": 0,
    "gain_cents": 0,
    "orders_kept": 0,
    "gigs_done": 0,
    "gigs_with_lower": 0,
    "saving_twin_cents": 0,
    "saving_lane_cents": 0,
    "cost_ratio_bound": 1.05
  },
  "quote": {
    "source": "probe",
    "gain_cents": 0,
    "probe": {
      "requests": 38,
      "skipped_rows": 0,
      "mismatched": 0,
      "days": [0, 1],
      "window": [544, 2790],
      "window_requests": 402,
      "week_requests": 1035,
      "scale": 10.58,
      "extrapolated": true,
      "won": 6,
      "lost": 3,
      "not_quoted": 29,
      "unwinnable": 0,
      "won_above_flip": 0,
      "flip_revenue_cents": 0,
      "won_revenue_cents": 0,
      "underpriced_cents": 0,
      "lost_winnable_cents": 0,
      "not_quoted_winnable_cents": 0,
      "window_gain_cents": 0,
      "week_gain_cents": 0
    },
    "brackets": {
      "lost_requests": 0,
      "lost_ceiling_cents": 0,
      "lost_bins": [{ "ratio": 1.2, "requests": 0, "ceiling_cents": 0 }],
      "lost_below_similar": { "requests": 0, "revenue_cents": 0 },
      "estimate": {
        "flip_revenue_cents": 0,
        "underpriced_cents": 0,
        "lost_winnable_cents": 0,
        "not_quoted_winnable_cents": 0,
        "week_gain_cents": 0
      }
    }
  },
  "on_time": {
    "counted": 0,
    "on_time": 0,
    "late": 0,
    "undelivered": 0,
    "share": 0.968,
    "ranked": true,
    "late_slack": 12,
    "drops_to_rank": 0
  },
  "combining": { "candidates": 0, "candidate_fee_cents": 0 },
  "oracle_cents": 0,
  "gap_cents": 0,
  "split": { "quoting_cents": 0, "driver_fees_cents": 0, "delivery_cents": 0, "combining_cents": null },
  "warnings": []
}
```

An `EXPERIMENT` (one per experiment and level) has `experiment`, `level`, `weeks`, `week_ids`, `ranked_weeks`, then
the same blocks with every cents value and count summed over its weeks. Shares and cost ratios are recomputed from
the sums; flags (`ranked_after`, `ranked`, `extrapolated`) become counts of weeks; `on_time.late_slack` is the
lowest of the weeks; `quote` adds `weeks_probe` and `weeks_brackets` (`source` is `"mixed"` when both occur), and
`quote.probe.window` is null. `per_week` holds the means per week of the margin, the four gains
(`selection_gain_cents` …), the oracle, the gap and each waterfall line (`per_week.waterfall`).
`analysis.oracle.build(db_path, probe_dir)` returns the same object for other scripts.

# Overview report

One static page with the whole picture of the scraped weeks, for deciding what to build next:

```sh
uv run python -m analysis.facts    # first: the facts tables
uv run python -m analysis.oracle   # optional: out/oracle.json, the gap bounds of section 5
uv run python -m analysis.report   # writes out/report.html and serves it on http://localhost:8000/
uv run python -m analysis.report --no-serve   # only writes out/report.html (for scripts)
uv run python -m analysis.report --port 8123 --db data/spread.sqlite --probe out/probe --oracle out/oracle.json --out out/report.html
```

By default it builds the page, writes it and serves it on localhost with the standard library's web server: it
prints the URL, and Ctrl-C stops it. `--port` picks the port (default 8000); if the port is taken it uses a free
one and prints that. The server serves only the page as it was built; run the command again for new data.
`--no-serve` writes the file and exits.

It opens the database read-only. `out/report.html` is one file with inline SVG, no JavaScript and no network, in
light and dark, one column on a phone, so it can also be opened or shared as a file. Without `out/oracle.json` it
calls `analysis.oracle` if that module exists, else section 5 shows only the account waterfall.

How to read it:

- **The strip at the top** has the five numbers that matter: the weeks scraped, the best mean margin at the highest
  played level, that experiment's on-time share, the median probe flip, and the biggest of the oracle's four gains
  in that experiment. That experiment (the best at the highest level) is the one the single-experiment charts show.
- **Every chart's title is its takeaway**, computed from the data ("Trust raises the win share from 32% to 74% at
  1.4–1.6 × list"), so it changes when the data does.
- **"Data and method"** under a chart holds what it counts, its caveats and its numbers as a table; "Method and
  caveats" under a section holds what applies to the whole section. Hover a point, bar or dot for its exact values.
- Sample sizes are in the axis labels and legends. Points with too few rows are not drawn (the line breaks) but
  stay in the data table.

1. **Experiments.** The margin of each week, one dot per week, filled when ranked (≥ 90% on time), a tick at the
   mean; an experiment far below all the others (the starter) gets its own panel with its own axis. The on-time
   share of each week against the 90% minimum. Counted orders by lateness. The table of all experiments is folded
   under the cards.
2. **Dealers: what price wins.** Share won against quote / list price, only on requests where we priced one option:
   by level, by dealer trust (level 8) and on the guessed price-war day (level 8). The level 8 curve by weekday is
   a folded table.
3. **Probe: where a quote flips.** From `out/probe`: the flip price of the first option at the level with the most
   probed requests (histogram), the flip by level and delivery option, and the fee probe (`fee-L*.jsonl`): the
   lowest flat fee, over the typical fee, at which a driver books a gig within the window. Without fee probe rows
   the third chart compares the probe with our own level 8 Monday quotes; with them that comparison is a sentence
   under "Method and caveats".
4. **Drivers: what fee books.** Level 8: the share of gigs booked within a day by opening fee (the booking rate by
   fee and level is a table under it), bookings per open daytime hour by hours left to the last pickup time, and
   the towns: drivers living there against the share of gig-days booked.
5. **Economics: where the margin goes.** For the experiment of the strip: revenue down to margin, and margin up to
   the oracle by the four bounds of `analysis.oracle`. For every experiment: the gap to the oracle as shares of the
   four bounds. The euros of all experiments and the assumptions of the bounds are folded.

Caveats: the win curves use only requests with one priced option (with several, each option's share reads about
half as high); the war day is a guess from the win share, so its gap is partly by construction; probe flips are
the first answers of a world that won nothing (no trust, no competitor reaction), and the fee probe is a small
sample; booking rates use only weeks with an action log, and their fee bands are not an experiment (a gig still
open at a high fee is a hard one); supply is an average over worlds, which level 8 reshuffles; the oracle's bars
are upper bounds, each under its stated assumptions, not forecasts.

# Offline replay

Runs every strategy of `strategies/` on the saved weeks, with no server and no key, and charts the results (#119):

```sh
uv run python -m analysis.replay              # writes out/replay.html and out/replay.csv, serves the page on http://localhost:8001/
uv run python -m analysis.replay --no-serve   # only writes the files
uv run python -m analysis.replay out/scrape/explore-win --jobs 2 --port 8123 --out out/replay.html --csv out/replay.csv
```

Without folders it reads every week under `out/scrape` (the team's release, see the main README) and `data/scrape`
(the committed weeks and our saved runs). It replays each played week that has a reveal, once per world: passive
weeks have no orders and are skipped. Weeks without a reveal, such as ranking runs (whose `reveal.json.gz` is empty),
are skipped too, and the console and the page's first line say how many. Saved runs of `dispatch.py` and of another system (the ladder) are separate
rows. It needs no database. The weeks run in parallel (`--jobs`, default the number of CPUs); the 288 played weeks of
the release and the repository take about 140 s on 4 CPUs. It plays nothing online.

There is no offline model of the world, so it replays the weeks: each week's recorded events go to each strategy in
order, as `dispatch.py` feeds them, and each decision is scored against what the week shows really happened. Where
the week cannot tell how a different decision would have ended, it counts as unknown, never as a guess. The
strategies are those of the checkout, so a branch can be compared with `main` by running it on both.

| Strategy  | What runs                                                                                                                                                                               | What it is scored on                                                                                                                                                                                            |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| notes     | `read_note` on every won car's note                                                                                                                                                     | each fact against the reveal's truth, with the scoring of `strategies/notes/check.py`, next to the starter's reader; the chart shows the facts a note changes                                                   |
| admission | `Desk.quote` of `dispatch.py` on every request: admission, the price it weighs, and the decline of a note whose deadline has passed. The desk holds only the orders it would have taken | the week's won orders split by whether the replay takes them: on-time share (as the score counts it, from the ledger's late refunds and penalties) and margin per order, from what happened to them in the week |
| pricing   | the prices of the same `Desk.quote`                                                                                                                                                     | each quote against the week's own for that request: at or under a price that won, it wins; at or over a price that lost, it loses; else unknown. Pricing learns only the answers that are known                 |
| fees      | `FeePlanner.schedule` for each gig of one order, from the minute the week posted it                                                                                                     | the fee its first driver booked at: where the plan reaches that fee by the minute they booked, it finds that driver too, and pays its first step at or over it; where it stays below, unknown                   |
| bundling  | the week's won orders through the `Bundler` pool, with `Desk.unit` of `dispatch.py`                                                                                                     | the share of orders in a chain, the driver-hours the chains save and the typical fees they save; against the share the week itself posted in gigs with several orders                                           |
| offers    | `Offers` with each gig the week posted, asked for offers at each post, delivery, drop and deadline warning and at least hourly                                                          | the week's bookings: the share whose driver got the replay's offer for that gig before booking it, and the share of offers that went to the driver who took the gig                                             |

The page has a scoreboard (one row per experiment, one headline number per strategy), then two charts per strategy:
one dot per week for the replay (filled) and, where there is one, the week's own number (ring), with the replay's
mean as a tick. The title of each chart is its takeaway, computed from the data; "Method" under it says what it
counts. `out/replay.csv` has one row per week, strategy and number (`experiment, level, seed, world, policy,
strategy, metric, value`). A strategy that fails on a week shows its error in a last section and leaves the others
to run.

Limits: the week's other decisions stay as they were. The orders admission declines still took drivers in the week,
so the kept orders' on-time share and margin are what they were with that competition. Pricing is scored at the
week's prices, so a replayed quote dearer than the week's winning one is unknown, and starter weeks (list price,
every option) can judge few quotes. Fees and offers get no answers from drivers, so a plan below what a driver took,
or an offer to a driver who did not book, is unknown.

## Pricing and fees on the probes, the starter and the saved weeks

The page has four more sections (#145). Two score pricing and fees where a week cannot: on `probe.py`'s rows in
`out/probe` (`--probe` for another folder), which come with the team's release. Each probed seed's request stream,
drivers and map are its passive week. Without probe rows, the two sections say so.

| Section                     | What runs                                                                                                                            | What it is scored on                                                                                                                                                           |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Pricing on the probes       | the desk's `PricingModel` through the seed's request stream on the probed days, each request quoted at its first option              | the quote flip of each probed request, the highest multiple of the list price that wins it: revenue won against the list price, every fixed multiple and the flip              |
| Fees on the probes          | the desk's `FeePlanner` and the starter's `BaselineFees` (strategies/baseline) for each fee-probed order, from the minute it was won | the fee flip, the lowest flat fee a driver booked within the probe's window: each schedule books at its first step at or over it before the last pickup, and pays that step    |
| Every strategy against none | nothing: each week's own score                                                                                                       | the starter's played weeks next to the saved runs of `dispatch.py`, the ladder and the TypeScript starter at one level: margin, revenue, orders, on time, ranked, fees per car |
| Every saved week            | nothing: each saved run's score and `meta.json`'s `version`                                                                          | margin and on-time share by the commit that played the week (grouped by `meta.json`'s policy), with the best and worst week of each seed                                       |

Pricing learns as in a week: a request without a probed flip wins or loses against a flip drawn from the same day's
probed requests (the same draws on every run), and only the probed requests are scored. Dealer trust stays at zero:
it needs deliveries. Fees plan at the order's list price. `out/replay.csv` has one more row per probed seed and number,
with the experiment `probe` and the strategy `pricing-probes` or `fees-probes`.

Limits: `probe.py`'s parent world wins nothing, so the competitor has not raised its prices for the probed dealers,
and the level 8 quote probes cover Monday and Tuesday only. A fee flip is the fee a driver took at the post: a
schedule that reaches it hours later may find that driver gone, and the starter's steep fees after a deadline warning
are left out. The starter's weeks and our saved runs are played on different seeds.
