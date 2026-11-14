# The volume gap

The top teams win about 1.4 times our orders at the same margin per order. Our margin per order is not the problem;
our volume is. No single threshold of ours closes the gap: moving one buys orders at about zero marginal margin. The
extra orders that pay are mostly requests we quote and lose, at prices that only knowing each request's limit would
find. What does transfer to a seed nobody has played is a set of selective levers, built in
[`strategies/volume`](../strategies/volume/README.md). Issue #304.

Measured offline on 14 November 2026 from the saved weeks (`out/spread.sqlite`, built from `data/scrape/runs`), the
server's fork probes (`data/scrape/probe2`), the shared leaderboards (`data/finals/2026-11-14-1400-test`) and the
simulator (`sim/`). "List" is a request's next-day list price. Money is game euros.

## The target

| Where                                  | Top 10 teams                                    | Us                                            |
| -------------------------------------- | ----------------------------------------------- | --------------------------------------------- |
| Ranking round 6, five shared worlds    | 2,160–2,343 orders, €39.7–44.5 an order, 93–99% | one run                                       |
| Round 6, world 1                       | 415–500 orders, €16.6k–21.3k                    | 270 orders, €11.7k (€43.4 an order), 94.1%    |
| Test final 14:00 (Thursday–Friday)     | 135–167 orders, €39–49 cost an order            | 69 orders (TypeScript `lean`), €47.8 an order |
| `strategies/all_in`, 39 practice weeks | —                                               | 334 orders a week, €39.5 an order, 97.5%      |

So the top teams need about 100–150 more orders a week than `all_in`, at about the same margin per order.

## Where our week goes

An offline replay of 31 saved `all_in` weeks through its own desk reproduces every quote to the cent, so each
request's fate is known. Of about 1,036 requests a week:

| Fate                        | Requests a week | Rule                                                           |
| --------------------------- | --------------: | -------------------------------------------------------------- |
| Won                         |             330 | 45.7% of the quotes                                            |
| Quoted, lost at the maximum |             164 | the moving maximum of `strategies/headroom/pricing.py`         |
| Quoted, lost at the learned |             167 | the learned price aims at a 45% win share                      |
| Quoted, lost at the floor   |              62 | driver cost × 1.1                                              |
| Declined for cost           |             228 | expected cost × 1.1 above the maximum (`strategies/lead_cost`) |
| Declined, no slack          |              39 | no option leaves 5 hours beyond the drive                      |
| Declined, area full         |              35 | `max(2, 0.20 × supply)` waiting cars near the pickup           |
| Declined, flu guard         |              12 | `strategies/flu_guard`                                         |

The five `all_in` ranking runs look the same: 263 declined, 772 quoted, 353 won a week.

## What the high-volume weeks won

`ts-recall` (TypeScript, in git history) remembers each request's winning and losing prices from earlier plays of
the same seed. Against `all_in` on six seeds (19 pairs), its weeks won 220 extra orders a week at €29.2 each (only
4–8% at a loss), and dropped 75 of ours at €28.8: 145 more orders and +€5,282 a week. It won 58–92% of the requests
it priced against our 39–52%, at the same average price over list. 62–86% of its extras are requests we quoted and
lost; it won them 7–17% under our price, exactly where the limit allowed. That knowledge does not exist on a secret
seed, but the weeks show which extra orders pay:

- **Lane length marks them.** Extras with a list under €40 made €10–17 an order, €70–100 made €32–40, €100 or more
  €46–60. A tree fitted on spread-1 picks this one split (a list under €40); dropping those extras gains on 4 of the
  5 other seeds.
- **Every extra order costs the rest of the book €7–14** in higher fees and lateness: with the fee planner held
  fixed, a car's fee rises 2.1% of its typical fee per 10 more orders a day, and 0.55 points more orders run late.
- **Drivers do not cap the volume.** `ts-recall` moved 500+ cars on spread-1 with 53% more driver-days, at the
  same 1.3 gigs per driver-day; the driver list holds them. Capacity is a tax, not a wall.

## What does not close it

Each of these was tested on the same seeds, so the requests are the same:

| Lever                                                   | Evidence                                                         | Result                      |
| ------------------------------------------------------- | ---------------------------------------------------------------- | --------------------------- |
| Lower prices everywhere                                 | server forks (`docs/world-facts.md`); simulator oracle, 31 seeds | −€67 / −€20–24 per extra    |
| Aim at 50% of quotes (`q-high50`)                       | 22 seeds against `k-all`                                         | +17 orders, −€107 a week    |
| A lower cost model (`p-92`, `p-86`)                     | 22 seeds against `k-all`                                         | +15/+19 orders, −€293/−€619 |
| Half the area room (`q-cap10`)                          | 22 seeds                                                         | −14 orders, −€171           |
| Five times the bundles (`bundling_more`)                | 3 seeds against its base                                         | −€27 to −€1,877             |
| Trust bought with Monday volume                         | `trust_value` 5 seeds, `trust_farm` 5 seeds                      | −€1,106, −€642 a week       |
| Quote every slower option (`option_menu`, on `ceiling`) | 3 seeds; dealers took the slower, cheaper options instead        | −€1,226 in total            |
| Expected-margin pricing (`profit_max`, on `ceiling`)    | 3 seeds; its win curve's width was assumed, not fitted           | −€1,574 in total            |

Nor do cheaper drivers explain the top weeks: no recorded policy pays materially less for the same cars. `all_in`
pays 0.96–1.01 of the per-car median; `ts-recall` paid 2–8% more than `all_in` on the orders both won. Direct
offers to drivers who finish near another pickup are read but declined at 85% of the app fee (0.5% accepted).

## What does

Two levers add orders without a lower price on the orders we already win, and hold on an unplayed seed. Both are in
`strategies/volume`:

1. **The option menu.** `all_in` quotes exactly one option per request, though about 500 requests a week offer two
   or three. The dealer takes the quoted option with the most headroom over its limit, and each option's limit has
   its own noise, so every option that pays its own driver cost is one more chance to win at the same price. Each
   option is priced over its own driver cost, and a quote with several options aims at 50% of its quotes, so that
   the learned price does not take the extra wins back as price. Simulator oracle, 31 seeds: +22 orders and
   +€1,393 a week at the same margin per order.
2. **Remote pickups cost less than we assume.** The saved weeks paid 0.68 of `all_in`'s expected cost for pickups
   where few drivers live (below the rest on 26 of 27 seeds). A pickup-scarcity term of 0.4 instead of 0.8 makes
   the realised cost flat across driver supply: about 12 more orders a week at €44 margin each.

On 30 fresh simulator seeds the two together made +€1,404 to +€1,782 a week over `all_in` with about 35 more orders,
at a slightly higher margin per order. A higher win share on long lanes (the requests with the margin room) and more
area room for them lost or did nothing there; `strategies/volume/README.md` has every comparison. Neither lever has
been played on the server yet.

## Corrections to what we measured before

- **The competitor's answer** is about a third of what `docs/world-facts.md` and `sim/world.ts` assume. A dealer's
  limit for us does not move while we win 30–70% of its requests in a day. Over 70% it falls 2.2%, 6.5%, 10.1% after
  one, two, three such days; under 30% it rises 2.7%, 5.7%, 6.5%. Our 10×-list declines count as losses for it, and
  only days with about 6 or more requests count. From 1.15 million single-option quotes on 30 seeds. The simulator's
  stronger answer tilts its volume comparisons against volume by about €850–1,350 a week.
- **Trust** counts at delivery and follows the rule's 1% an order. `all_in` already turns it into price, worth
  €2,941 a week. The top dealer sends 30% of all requests (307 a week) and reaches trust 18–22 by Wednesday at any
  win share of 30% or more, so volume does not buy more trust there.
- **A late order early in the week** costs the top dealer €216–325 (Tuesday or Wednesday) through lost trust and
  its 2.5% penalty, against a refund of about €55.
- **Monday at trust 0**, the dealer's limit sits within 8.6% (sd) of `all_in`'s quote: 5% lower wins 76% of those
  quotes instead of 51%.
- **The lead-cost model** is about 15% above what the saved weeks paid almost everywhere (0.858 on 10,081 orders).
  That cushion pays for the displacement extra orders cause, so only the segments overstated beyond it (remote
  pickups 0.68, 60 hours or more to the last pickup 0.79) are worth correcting.

## Not measured

Three planned angles did not finish: whether the server's dealers take any quoted option under its limit (the
option menu's premise; the simulator assumes so, fitted almost only on single-option quotes), how far a model
learned inside one week can predict each request's limit, and the level-8 events (outage, price war, flu, bulk
order) as volume.
