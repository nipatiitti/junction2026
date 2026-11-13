# Facts: derived analysis tables

## What it is

Derived tables in the scrape database, so that a question about the world is one SQL query. They are built from
the raw tables of `db.py` (see the main README) and live in the same file:

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

| Column | Meaning |
|---|---|
| `week_id`, `world_id`, `seed`, `level`, `policy` | from `weeks` |
| `experiment` | the folder after `scrape/` (`passive`, `explore-win`, `explore-ceiling`, `starter`…), else the policy |
| `recorded` | 1 when the week has an action log (`actions` rows) |
| `quote_share`, `fee_shape`, `fee_cap`, `offers` | the explore settings (`weeks.settings`) |
| `quote_lo`, `quote_hi`, `fee_lo`, `fee_hi` | the explore ranges |
| `drivers`, `drivers_experienced`, `drivers_manual`, `towns_with_drivers` | the driver list at the start |
| `requests`, `quoted`, `declined`, `unquoted` | requests; with a real quote; only declined (≥ 5 × list); never answered |
| `won`, `cancelled`, `counted`, `delivered`, `on_time`, `late`, `undelivered` | orders, from `order_facts` |
| `on_time_share` | `on_time / counted` (equals `weeks.on_time_share`) |
| `late_slack` | `counted // 10 - (late + undelivered)`: more late orders the week can take and stay at 90%; negative = not ranked |
| `revenue_cents` … `fine_cents`, `other_cents` | ledger sums by kind, signed as in the ledger (costs negative) |
| `margin_cents` | sum of every ledger line (equals `weeks.margin_cents`) |
| `gigs`, `bookings`, `drops`, `no_shows`, `expired`, `views` | gigs; `gig_booked`, `gig_dropped`, `no_show`, `gig_expired` events; views |
| `war_day` | the day `week_days` guesses as the price war, else null |
| `facts_version` | the builder's `VERSION` |

### `quote_facts`: one row per delivery option of each request (the win model)

| Column | Meaning |
|---|---|
| `week_id`, `level`, `request_id`, `option` | the option (`same_day`, `next_day`, `within_3_days`) |
| `dealer_id`, `batch_id`, `batch_size` | the dealer; requests in the same batch (1 without one) |
| `arrived_at`, `respond_by`, `day`, `hour` | when the request came; `day`, `hour` of `arrived_at` |
| `legs` | cars of the request (2 = trade-in) |
| `pickup_place`, `delivery_place`, `km` | leg 0 |
| `km_total`, `minutes_total` | over all legs |
| `private_pickup`, `private_delivery`, `premium`, `electric` | true on any leg |
| `low_charge` | an electric car under 30% going over 200 km (needs a charging stop) |
| `has_note`, `note_language` | the request has a note; its language |
| `options_offered`, `option_rank` | options of the request; 0 same day, 1 next day, 2 within three days |
| `deadline`, `hours_to_deadline` | the option's deadline; hours from arrival to it |
| `lead_minutes` | leg 0 ready time minus arrival |
| `list_price_cents`, `reference_fee_cents`, `fee_share` | list price; typical driver fee of the request; their ratio |
| `quote_cents`, `ratio` | our last quote (null when not priced); quote over list |
| `declined`, `quoted` | `ratio >= 5` (a decline); a real quote |
| `options_quoted`, `cheapest`, `min_other_ratio` | quoted options of the request; this is the cheapest; the lowest ratio among the others |
| `outcome`, `taken` | `won`, `lost`, `unquoted`; the dealer took this option from us |
| `dealer_trust` | the dealer's trust count at the decision, rebuilt from revenue and refund lines (+1 on time up to 25, halved when late) |
| `dealer_on_time_before`, `dealer_late_before` | our orders for this dealer delivered on time / late before the decision |
| `dealer_open_orders`, `dealer_overdue_open` | its orders won and not delivered; those past their deadline |
| `dealer_requests_before`, `dealer_quoted_before`, `dealer_won_before`, `dealer_unquoted_before` | the dealer's earlier decided requests of the week |
| `drivers_pickup`, `drivers_delivery`, `drivers_near_pickup`, `drivers_near_delivery` | drivers living at / near leg 0's places |
| `war_guess` | the request came on the guessed price-war day |

### `order_facts`: one row per won order (cancelled included)

| Column | Meaning |
|---|---|
| `week_id`, `level`, `order_id`, `dealer_id`, `option` | |
| `won_at`, `day`, `hour` | when we won it |
| `legs`, `pickup_place`, `delivery_place`, `km`, `km_total`, `private_pickup`, `private_delivery`, `premium`, `electric`, `has_note` | the request's lane and cars |
| `price_cents`, `list_price_cents`, `ratio`, `reference_fee_cents` | our price; the taken option's list price; their ratio; typical fee |
| `deadline_won`, `last_pickup_won`, `deadline` | deadline and last pickup at the win; the deadline at the end |
| `changes`, `place_changed` | changes of plan; one of them moved a place |
| `ready_late`, `held`, `needs_plates`, `manual_gearbox`, `summer_tyres`, `note_deadline`, `hours_differ` | the truth behind the note (reveal) |
| `status`, `cancelled`, `cancelled_at`, `counted` | status at the end; cancelled; when; counts for the delivery minimum |
| `delivered_at` | minute of its revenue line |
| `revenue_cents` … `other_cents` | its ledger lines by kind, signed |
| `extra_driving_cents` | the part of `driver_fee_cents` paid for extra driving after a change of plan |
| `margin_cents` | sum of the account columns |
| `refund_pct`, `late_minutes` | from the late refund line; `late_minutes` is 0 when on time |
| `late_bucket` | `on_time`, `le_2h`, `le_24h`, `le_2bd`, `gt_2bd`, `late_other`, `undelivered`, `cancelled` |
| `on_time` | null when cancelled |
| `gigs`, `bookings`, `drops`, `no_shows`, `expired`, `reprices`, `failed_visits`, `views`, `viewers` | over the gigs that carry it |
| `shared_gig` | a gig of it also carries another order |
| `first_posted_at`, `minutes_to_post`, `first_fee_ratio` | its first gig; minutes from the win; its opening fee over the typical fee |
| `first_view_fee_cents` | the fee a driver saw first (what drivers learn from) |
| `first_booked_at`, `minutes_to_booking`, `first_booked_ratio` | the first booking; minutes from the first post; fee over typical |
| `paid_ratio` | driver fees paid (without extra driving) over the typical fee |
| `open_minutes` | minutes its gigs were open |
| `dealer_trust_won` | the dealer's trust count when we won it |

### `gig_facts`: one row per gig (fee bound, how low drivers go, where bookers live)

| Column | Meaning |
|---|---|
| `week_id`, `level`, `gig_id`, `source` | `source`: `actions` (fees rebuilt from the action log) or `gigs` (last schedule only) |
| `order_id`, `orders`, `cars`, `order_post_no` | first stop's order; orders and cars in it; 1 for the order's first gig, 2 for the next… |
| `pickup_place`, `delivery_place`, `km`, `drive_minutes` | first pickup, last delivery, over its cars |
| `private_pickup`, `private_delivery`, `premium`, `experienced`, `manual_licence`, `with_plates`, `with_charging` | its cars and audience |
| `posted_at`, `posted_day`, `posted_hour` | |
| `typical_fee_cents` | the typical fee for its cars |
| `opening_fee_cents`, `opening_ratio`, `top_fee_cents` | first step of the first schedule; over typical; last step of the last schedule |
| `steps`, `reprices` | steps of the first schedule; reprices |
| `spells`, `open_minutes` | its `gig_spells` rows; minutes open |
| `views`, `viewers`, `bookings`, `drops`, `no_shows`, `failed_visits` | |
| `first_booked_at`, `first_booked_fee_cents`, `minutes_to_booking` | the first booking |
| `outcome` | `open`, `booked`, `working`, `done`, or for a withdrawn gig `expired`, `cancelled`, `released`, `withdrawn` |
| `driver_id`, `booked_at`, `fee_cents`, `fee_ratio` | the last booking (null without a driver) |
| `paid_cents`, `started_at` | driver fees paid (positive); last start |
| `last_pickup_at_post`, `minutes_to_last_pickup` | the order's last pickup known at the post; minutes left |
| `driver_home`, `home_to_pickup_km`, `delivery_to_home_km` | where the driver lives; road km to the pickup and back home |

### `gig_spells`: one row per period a gig was open at one fee within one day (the booking hazard)

| Column | Meaning |
|---|---|
| `week_id`, `level`, `gig_id`, `spell`, `source` | `spell` numbers the gig's rows in time order |
| `fee_run` | rows with one `fee_run` are one period at one fee, cut at midnight |
| `interval` | open intervals of the gig: a new one after each drop or no-show |
| `order_id`, `order_post_no`, `cars`, `orders`, `pickup_place`, `delivery_place`, `km`, `drive_minutes`, `private_pickup`, `premium`, `experienced`, `manual_licence` | of the gig |
| `start_at`, `end_at`, `minutes`, `day_minutes` | the period; its minutes; those between 07:00 and 23:00 |
| `day`, `hour` | of `start_at` |
| `fee_cents`, `typical_fee_cents`, `fee_ratio`, `next_fee_cents` | the fee shown; typical; ratio; the next row's fee after a raise, reprice or midnight |
| `last_pickup_at`, `minutes_to_last_pickup`, `deadline_warned` | the order's last pickup known at `start_at`; minutes left; a `deadline_close` came |
| `opened_by` | `post`, `drop`, `no_show` |
| `order_age_minutes` | minutes since the order's first gig was posted |
| `views`, `viewers`, `new_viewers` | views in the row; drivers; drivers who had not seen the order before |
| `order_views_before`, `order_viewers_before`, `order_viewed_before` | views of the order's gigs before `start_at` |
| `first_view_fee_cents`, `fee_over_first_view` | the order's first viewed fee (before `start_at`); this fee over it |
| `order_bookings_before` | earlier bookings of the order's gigs |
| `taught_orders`, `taught_raise`, `taught_wait` | the week's bookings so far; their mean fee over the first viewed fee and mean minutes after it |
| `drivers_pickup`, `drivers_near_pickup`, `snow` | drivers at / near the pickup; snow forecast there |
| `offers` | direct offers sent during the row |
| `end_kind` | `booked`, `raise`, `reprice`, `midnight`, `expired`, `withdrawn`, `cancelled`, `end` |
| `end_estimated` | the end is a guess (a withdraw without the action log) |
| `booked`, `driver_id`, `booked_fee_cents`, `via_offer` | the booking that ended the row |
| `kept` | the booking held to the end (no drop, no-show, release or cancellation) |
| `view_fee_mismatches` | views in the row that saw another fee |

### `town_days`: one row per week, place and day 0–9 (supply)

| Column | Meaning |
|---|---|
| `week_id`, `level`, `place`, `day` | |
| `drivers_home`, `experienced_home`, `manual_home`, `drivers_near` | drivers living there / near |
| `snow` | a forecast covers the place that day |
| `requests`, `requests_delivery`, `won` | requests that day picking up / delivering there; orders won picking up there |
| `viewers_home`, `views_home`, `bookers_home`, `bookings_home`, `starters_home` | drivers living there who viewed, booked, started a gig that day |
| `gigs_posted`, `gigs_open`, `open_minutes` | gigs picking up there: posted; open; minutes open |
| `views`, `viewers`, `bookings`, `booked_share` | views and bookings of those gigs; bookings per open gig |
| `mean_booked_ratio`, `min_booked_ratio` | booked fee over typical fee |

Passive weeks fill only the drivers, snow and requests columns.

### `week_days`: one row per week and weekday 0–4 (day effects, the price war)

| Column | Meaning |
|---|---|
| `week_id`, `level`, `day` | |
| `requests`, `quoted`, `won` | requests arriving that day; quoted; won |
| `band_n`, `band_won`, `band_share` | real quotes at 1.0–1.25 × list between 08:00 and 18:00; those taken; their share |
| `war_score` | `band_share` minus the mean of the week's other days (with 10+ quotes in the band) |
| `war_guess` | the day with the lowest score, at level 8, when it is −0.25 or lower |

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

## For the hindsight oracle (#66)

- Waterfall: the account columns of `week_facts`; on-time slack: `week_facts.late_slack`.
- Selection bound: `order_facts.margin_cents > 0`; delivery bound: `price_cents` and `driver_fee_cents` of `order_facts`.
- Fee bound: `gig_facts` rows with `outcome = 'done'`, lowest `fee_ratio` by `pickup_place`, `delivery_place`, `posted_day`.
- Quote brackets: `quote_facts.ratio` against `taken` by lane and day.

## Overview report

One static page with the whole picture of the scraped weeks:

```sh
uv run python -m analysis.facts    # first: the facts tables
uv run python -m analysis.oracle   # optional: out/oracle.json, the gap bounds of section 6
uv run python -m analysis.report   # writes out/report.html
uv run python -m analysis.report --db data/spread.sqlite --probe out/probe --oracle out/oracle.json --out out/report.html
```

It opens the database read-only. Open `out/report.html` in a browser or share the file: it is one file with inline
SVG, no JavaScript and no network, in light and dark, one column on a phone. Hover a point, bar or dot for its exact
values; each chart's numbers are under "Data". Without `out/oracle.json` it calls `analysis.oracle` if that module
exists, else section 6 shows only the account waterfall. Points with too few rows are not drawn (the line breaks)
but stay in the data table.

1. **Experiments.** Which experiment and level made or lost how much, and how many of its weeks would have been
   ranked. Table per experiment and level; *Margin of each week*: one dot per week, filled when ranked (≥ 90% on
   time), hollow when not, a tick at the mean.
2. **Dealers: the win curve.** Share won against quote / list price, only on requests where we priced one option.
   *By level*: level 8 pays well above list. *By weekday, level 8*: later days win at higher prices: dealers trust
   us more, and the competitor raises its prices for dealers it keeps winning. *The price-war day*: on one day a
   week the competitor quotes 20% lower (the day is a guess). *By dealer trust*: each on-time order raises what its
   dealer accepts by 1%, up to 25; a late order halves the count.
3. **Probe: where a quote flips.** The exact price at which a request flips from won to lost in one world, from
   `out/probe`. Tiles: probed requests, median flip, share below list, share never won. *Flip price of the first
   option* (histogram); *Flip by delivery option*: slower options flip lower, the dealer pays for speed; *Probe
   against our quotes, level 8 Mondays*: the same curve from two sources.
4. **Drivers: the booking curve.** Bookings per open daytime hour (a rate, not a share). *By fee over the typical
   fee*; *By hours to the last pickup time, level 8*: the deadline warning comes at 3 hours, after that only a
   higher fee finds a driver; *Share of gigs booked within a day of posting, by opening fee*: the plain reading.
5. **Supply by town.** *Drivers at home and booked share by town, level 8*: where the drivers live in a shortage
   world and where gigs get booked (a gig-day is one gig open on one day).
6. **Order economics.** Per experiment: *Where the money went (mean week)*, revenue down to margin; *What a perfect
   dispatcher keeps (mean week, upper bounds)*, margin up to the oracle by the four bounds of `analysis.oracle`,
   with their assumptions and the brief's split; a table over all experiments.
7. **On time.** *On-time share of each week* against the 90% minimum; *Counted orders by lateness*, with the refund
   of each bucket; a table with counts, slack, refunds and penalties.

Caveats: the win curves use only requests with one priced option (with several, each option's share reads about
half as high); the war day is a guess from the win share, so its gap is partly by construction; probe flips are
the first answers of a world that won nothing (no trust, no competitor reaction); booking rates use only weeks
with an action log; supply is an average over worlds, which level 8 reshuffles; the oracle's bars are upper bounds,
each under its stated assumptions, not forecasts.
