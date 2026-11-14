# Strategies

Each folder here is one strategy: one part of the decisions that `dispatch.py` makes. Every strategy is a subclass of
the abstract base class `Strategy` in [`strategy.py`](strategy.py), so they are all built, fed and read the same way.

| Folder                              | Class               | What it decides                                                 |
| ----------------------------------- | ------------------- | --------------------------------------------------------------- |
| [`notes/`](notes/README.md)         | `NoteReader`        | What a dealer's note says, and the snow that a pickup waits for |
| [`admission/`](admission/README.md) | `Admission`         | Which price requests to take, and which option to quote         |
| [`pricing/`](pricing/README.md)     | `PricingModel`      | The price of each quote, learned from our wins and losses       |
| [`fees/`](fees/README.md)           | `FeePlanner`        | The fee schedule of each gig                                    |
| [`offers/`](offers/README.md)       | `Offers`            | Direct offers to drivers near a gig's pickup                    |
| [`bundling/`](bundling/README.md)   | `Bundler`           | Which orders' cars go together in one gig                       |
| [`dawn_fees/`](dawn_fees/README.md) | `DawnFeePlanner`    | The fee schedule by the drivers' day, for `headroom` and up     |
| [`lead_cost/`](lead_cost/README.md) | `LeadCostAdmission` | Which requests to take, by lead time, for `headroom` and up     |
| [`lane_fee/`](lane_fee/README.md)   | `LaneFee`           | A lane's typical fee without one request's noise, for the same  |

there is that system's, not `dispatch.py`'s. None of them changes the folders above.

| Folder                                            | Classes                                | What it is                                                                              |
| ------------------------------------------------- | -------------------------------------- | --------------------------------------------------------------------------------------- |
| [`baseline/`](baseline/README.md)                 | `BaselineAdmission`, `BaselineFees`, … | The organisers' starter as strategies: our fixed baseline                               |
| [`price_ladder/`](price_ladder/README.md)         | `LadderPricing`, `ShadowAdmission`     | A clamped price ladder with a shadow price on capacity                                  |
| [`city_ladder/`](city_ladder/README.md)           | `CityLadderPricing`                    | The price ladder with one position per pickup city                                      |
| [`dealer_ladder/`](dealer_ladder/README.md)       | `DealerLadderPricing`                  | The price ladder with one position per dealer                                           |
| [`dealer_streak/`](dealer_streak/README.md)       | `DealerStreakPricing`                  | The dealer ladder with a step that grows with the dealer's run of wins and losses       |
| [`streak_ladder/`](streak_ladder/README.md)       | `StreakLadderPricing`                  | The price ladder with a step that grows with the run of wins and losses, more on a loss |
| [`scarcity_cost/`](scarcity_cost/README.md)       | `ScarcityAdmission`                    | Admission with the town's quotas per driver priced in                                   |
| [`bundling_more/`](bundling_more/README.md)       | `WaitingBundler`                       | Every order waits for a chain, so more cars share a gig                                 |
| [`learned_hold/`](learned_hold/README.md)         | `AdaptiveHoldBundler`                  | Headroom, with each order's wait learned from its pickup town's bookings                |
| [`bundling_cheaper/`](bundling_cheaper/README.md) | `CheapBundler`                         | A bundle keeps a smaller share of its cars' solo bill                                   |
| [`ratchet/`](ratchet/README.md)                   | `RatchetPricing`, `TrustAdmission`, …  | A price ratchet per dealer and flat fees priced by risk                                 |
| [`ceiling/`](ceiling/README.md)                   | `CeilingPricing`, `ChainAdmission`     | Prices just under a maximum, over the driver cost, with timed return legs               |
| [`delivery_urgency/`](delivery_urgency/README.md) | `UrgencyPricing`, `UrgencyAdmission`   | The ladder's quote priced by the delivery option's kind                                 |
| [`special_premium/`](special_premium/README.md)   | `SpecialPricing`, `SpecialAdmission`   | Urgency plus a compounding +5% per special requirement, on the quote and the driver fee |
| [`scarcity_urgency/`](scarcity_urgency/README.md) | `ScarcityUrgencyAdmission`             | The town's scarcity and the urgency quote in one folder                                 |
| [`scarcity_ceiling/`](scarcity_ceiling/README.md) | `ChainScarcityAdmission`               | The ceiling's quote over the scarcity-priced admission                                  |
| [`profit_max/`](profit_max/README.md)             | `ProfitPricing`                        | Ceiling, quoting the price with the most expected margin on a win curve                 |
| [`learned_cost/`](learned_cost/README.md)         | `LearnedCostAdmission`                 | Ceiling, with the driver cost corrected by our own bookings, by town                    |
| [`learned_notes/`](learned_notes/README.md)       | `LearnedNoteReader`                    | Headroom, adding reviewed data-fitted phrases after the base note rules                |
| [`trust_value/`](trust_value/README.md)           | `TrustValueAdmission`                  | Ceiling, counting the dealer trust that an order on time buys                           |
| [`war_guard/`](war_guard/README.md)               | `WarGuardPricing`, `WarGuardAdmission` | Ceiling, undoing the price war's lessons and widening the outage                        |
| [`war_sweep/`](war_sweep/README.md)               | `WarSweepPricing`                      | Headroom, capping quotes in a detected price war without adding capacity                |
| [`option_menu/`](option_menu/README.md)           | `OptionMenu`                           | Ceiling, quoting admission's option and every slower one                                |
| [`slack_fees/`](slack_fees/README.md)             | `SlackFeePlanner`                      | Ceiling, with the early fee held for cars that have a day to wait                       |
| [`tempo/`](tempo/README.md)                       | `TempoAdmission`                       | Ceiling, with each area's capacity set by how fast our gigs book there                  |
| [`max_margin/`](max_margin/README.md)             | `MaxPricing`                           | Slack fees and the war guard, pricing up to 2.0 x the list price by option and lane     |
| [`tight_margin/`](tight_margin/README.md)         | `TightPricing`                         | Max margin's prices only once the week's drivers fall behind                            |
| [`low_opening/`](low_opening/README.md)           | `LowOpeningPlanner`                    | Slack fees, opening a patient gig's first post at 0.8 x the typical fee                 |
| [`headroom/`](headroom/README.md)                 | `HeadroomPricing`                      | Ceiling, with the lane fee, the cost by lead time, dawn fees and a maximum that moves   |
| [`chain_opt/`](chain_opt/README.md)               | `RouteBundler`                         | Headroom, with chains built by cheapest insertion instead of appending each next order  |
| [`trust_farm/`](trust_farm/README.md)             | `TrustFarmPricing`, `TrustFarmAdmission` | Headroom, farming busy dealers' trust on discounted easy orders, then harvesting it     |
| [`outage_harvest/`](outage_harvest/README.md)     | `OutageAdmission`, `OutagePricing`     | Headroom, reserving shared driver capacity for the flagged outage region               |
| [`contextual_mix/`](contextual_mix/README.md)     | `ContextualPricing`                   | Headroom, switching to a lower price cap where a pickup town's gigs book slowly          |
| [`bulk_yard/`](bulk_yard/README.md)               | `BulkYardAdmission`, `BulkYardBundler` | Headroom, admitting a large yard batch as one and planning its chains from the yard      |
| [`lane_prior/`](lane_prior/README.md)             | `PriorPricing`                         | Headroom, with a lift for each dear delivery place, fitted on the saved weeks           |
| [`town_open/`](town_open/README.md)               | `TownOpening`, `TownFeePlanner`        | Headroom, with the opening fee of each pickup town learned from its bookings            |
| [`same_day/`](same_day/README.md)                 | `SameDayAdmission`                     | Headroom, quoting the fastest option that still pays                                    |
| [`soft_top/`](soft_top/README.md)                 | `SoftTopPlanner`                       | Headroom, with a top fee of twice the lane fee, not 2.5 times                           |
| [`combined_fees/`](combined_fees/README.md)       | `CombinedTopPlanner`                   | Soft top with the homecoming and on-time-slack discounts                                |
| [`drop_risk/`](drop_risk/README.md)               | `DropRiskFeePlanner`                   | Headroom, with higher, flatter fees where booked drivers drop their gigs                |
| [`slack_budget/`](slack_budget/README.md)         | `SlackBudgetAdmission`                 | Headroom, spending on-time slack above a reserve and refusing known risks at it       |
| [`snow_aware/`](snow_aware/README.md)             | `SnowPlanner`, `SnowBundler`           | Headroom, stretching snowy legs and opening snowy pickup gigs earlier and dearer       |
| [`opening_offers/`](opening_offers/README.md)     | `OpeningOffers`                        | Direct offers to nearby homes from a gig's first post, at the chain-offer fee           |
| [`home_return/`](home_return/README.md)           | `HomeReturnFees`                       | A discounted fee where many drivers live at the delivery town                           |
| [`adaptive_fees/`](adaptive_fees/README.md)       | `AdaptiveFees`                         | Cheaper fees while the running on-time share is above 95%, normal fees below it         |
| [`hazard_fee/`](hazard_fee/README.md)             | `HazardFeePlanner`                     | Headroom, opening at the cheapest fee whose observed booking hazard meets a target      |
| [`hazard_admission/`](hazard_admission/README.md) | `LeadCostAdmission`                    | The root system with admission's driver cost fitted by lead time                        |
| [`ifs/`](ifs/README.md)                           | `IfRules`, `IfFees`                    | Plain if rules with every number in one file, and a search that plays for better ones   |
| [`joint_bid/`](joint_bid/README.md)               | `JointPricing`, `JointFeePlanner`      | Headroom, quoting over the expected fee of the schedule the fee planner will post       |
| [`pair_first/`](pair_first/README.md)             | `PairFirstAdmission`                   | Headroom, pricing an assumed chain saving when a held order can pair with the request   |
| [`robust_tune/`](robust_tune/README.md)           | `RobustPricing`                        | Headroom with one slower world estimate and no place or dealer offsets by default       |
| [`herd_competitor/`](herd_competitor/README.md)   | `HerdPricing`                          | Headroom, losing a dealer's low-margin requests when our rolling win share gets too high |
| [`offer_probe/`](offer_probe/README.md)           | `ProbeOffers`                          | Headroom, offering only to active drivers and learning acceptance by fee ratio           |
| [`outage_harvest/`](outage_harvest/README.md)     | `OutageAdmission`, `OutagePricing`     | Headroom, reserving shared driver capacity for the flagged outage region               |
| [`contextual_mix/`](contextual_mix/README.md)     | `ContextualPricing`                   | Headroom, switching to a lower price cap where a pickup town's gigs book slowly          |
Fifty-three folders are whole systems of their own: each holds a dispatcher plus its own strategies, so a week played
there is that system's, not `dispatch.py`'s. None of them changes the folders above.

| Folder                                            | Classes                                | What it is                                                                               |
| ------------------------------------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------- |
| [`baseline/`](baseline/README.md)                 | `BaselineAdmission`, `BaselineFees`, … | The organisers' starter as strategies: our fixed baseline                                |
| [`price_ladder/`](price_ladder/README.md)         | `LadderPricing`, `ShadowAdmission`     | A clamped price ladder with a shadow price on capacity                                   |
| [`city_ladder/`](city_ladder/README.md)           | `CityLadderPricing`                    | The price ladder with one position per pickup city                                       |
| [`dealer_ladder/`](dealer_ladder/README.md)       | `DealerLadderPricing`                  | The price ladder with one position per dealer                                            |
| [`dealer_streak/`](dealer_streak/README.md)       | `DealerStreakPricing`                  | The dealer ladder with a step that grows with the dealer's run of wins and losses        |
| [`streak_ladder/`](streak_ladder/README.md)       | `StreakLadderPricing`                  | The price ladder with a step that grows with the run of wins and losses, more on a loss  |
| [`scarcity_cost/`](scarcity_cost/README.md)       | `ScarcityAdmission`                    | Admission with the town's quotas per driver priced in                                    |
| [`bundling_more/`](bundling_more/README.md)       | `WaitingBundler`                       | Every order waits for a chain, so more cars share a gig                                  |
| [`bundling_cheaper/`](bundling_cheaper/README.md) | `CheapBundler`                         | A bundle keeps a smaller share of its cars' solo bill                                    |
| [`ratchet/`](ratchet/README.md)                   | `RatchetPricing`, `TrustAdmission`, …  | A price ratchet per dealer and flat fees priced by risk                                  |
| [`ceiling/`](ceiling/README.md)                   | `CeilingPricing`, `ChainAdmission`     | Prices just under a maximum, over the driver cost, with timed return legs                |
| [`delivery_urgency/`](delivery_urgency/README.md) | `UrgencyPricing`, `UrgencyAdmission`   | The ladder's quote priced by the delivery option's kind                                  |
| [`special_premium/`](special_premium/README.md)   | `SpecialPricing`, `SpecialAdmission`   | Urgency plus a compounding +5% per special requirement, on the quote and the driver fee  |
| [`scarcity_urgency/`](scarcity_urgency/README.md) | `ScarcityUrgencyAdmission`             | The town's scarcity and the urgency quote in one folder                                  |
| [`scarcity_ceiling/`](scarcity_ceiling/README.md) | `ChainScarcityAdmission`               | The ceiling's quote over the scarcity-priced admission                                   |
| [`profit_max/`](profit_max/README.md)             | `ProfitPricing`                        | Ceiling, quoting the price with the most expected margin on a win curve                  |
| [`learned_cost/`](learned_cost/README.md)         | `LearnedCostAdmission`                 | Ceiling, with the driver cost corrected by our own bookings, by town                     |
| [`learned_notes/`](learned_notes/README.md)       | `LearnedNoteReader`                    | Headroom, adding reviewed data-fitted phrases after the base note rules                  |
| [`trust_value/`](trust_value/README.md)           | `TrustValueAdmission`                  | Ceiling, counting the dealer trust that an order on time buys                            |
| [`war_guard/`](war_guard/README.md)               | `WarGuardPricing`, `WarGuardAdmission` | Ceiling, undoing the price war's lessons and widening the outage                         |
| [`war_sweep/`](war_sweep/README.md)               | `WarSweepPricing`                      | Headroom, capping quotes in a detected price war without adding capacity                 |
| [`option_menu/`](option_menu/README.md)           | `OptionMenu`                           | Ceiling, quoting admission's option and every slower one                                 |
| [`slack_fees/`](slack_fees/README.md)             | `SlackFeePlanner`                      | Ceiling, with the early fee held for cars that have a day to wait                        |
| [`tempo/`](tempo/README.md)                       | `TempoAdmission`                       | Ceiling, with each area's capacity set by how fast our gigs book there                   |
| [`max_margin/`](max_margin/README.md)             | `MaxPricing`                           | Slack fees and the war guard, pricing up to 2.0 x the list price by option and lane      |
| [`tight_margin/`](tight_margin/README.md)         | `TightPricing`                         | Max margin's prices only once the week's drivers fall behind                             |
| [`low_opening/`](low_opening/README.md)           | `LowOpeningPlanner`                    | Slack fees, opening a patient gig's first post at 0.8 x the typical fee                  |
| [`headroom/`](headroom/README.md)                 | `HeadroomPricing`                      | Ceiling, with the lane fee, the cost by lead time, dawn fees and a maximum that moves    |
| [`outage_harvest/`](outage_harvest/README.md)     | `OutageAdmission`, `OutagePricing`     | Headroom, reserving shared driver capacity for the flagged outage region                 |
| [`contextual_mix/`](contextual_mix/README.md)     | `ContextualPricing`                    | Headroom, switching to a lower price cap where a pickup town's gigs book slowly          |
| [`bulk_yard/`](bulk_yard/README.md)               | `BulkYardAdmission`, `BulkYardBundler` | Headroom, admitting a large yard batch as one and planning its chains from the yard      |
| [`lane_prior/`](lane_prior/README.md)             | `PriorPricing`                         | Headroom, with a lift for each dear delivery place, fitted on the saved weeks            |
| [`same_day/`](same_day/README.md)                 | `SameDayAdmission`                     | Headroom, quoting the fastest option that still pays                                     |
| [`soft_top/`](soft_top/README.md)                 | `SoftTopPlanner`                       | Headroom, with a top fee of twice the lane fee, not 2.5 times                            |
| [`flu_guard/`](flu_guard/README.md)               | `FluGuardAdmission`                    | Soft top, with a guard against the week's flu day, which shows at midnight               |
| [`all_in/`](all_in/README.md)                     | `AllInAdmission`, `AllInPlanner`       | Soft top with the lane priors, same-day quotes, the flu guard and fees tuned on 22 weeks |
| [`slack_budget/`](slack_budget/README.md)         | `SlackBudgetAdmission`                 | Headroom, spending on-time slack above a reserve and refusing known risks at it          |
| [`snow_aware/`](snow_aware/README.md)             | `SnowPlanner`, `SnowBundler`           | Headroom, stretching snowy legs and opening snowy pickup gigs earlier and dearer         |
| [`opening_offers/`](opening_offers/README.md)     | `OpeningOffers`                        | Direct offers to nearby homes from a gig's first post, at the chain-offer fee            |
| [`home_return/`](home_return/README.md)           | `HomeReturnFees`                       | A discounted fee where many drivers live at the delivery town                            |
| [`adaptive_fees/`](adaptive_fees/README.md)       | `AdaptiveFees`                         | Cheaper fees while the running on-time share is above 95%, normal fees below it          |
| [`hazard_admission/`](hazard_admission/README.md) | `LeadCostAdmission`                    | The root system with admission's driver cost fitted by lead time                         |
| [`ifs/`](ifs/README.md)                           | `IfRules`, `IfFees`                    | Plain if rules with every number in one file, and a search that plays for better ones    |

[`bench/`](bench/README.md) is not a strategy either: it compares versions of `dispatch.py` on the same seeds.
[`tournament/`](tournament/README.md) plays the ceiling system with several of the folders built on it at once, and
finds the best mix of them in rounds.
[`leaderboard/`](leaderboard/README.md) plays every strategy, Python and TypeScript, online on `spread-1` and charts
their margins; it replays only the strategies that are new or whose code changed.

## The base class

- **One constructor.** Every strategy takes `(roster, world_map, level=8, params=None)`: the driver list and the map
  that the desk loads once when it starts, the level, and the strategy's `Params`. Without `params` it uses its own
  defaults, the tuned thresholds.
- **`params`.** A frozen dataclass of the strategy's thresholds, named `Params` in its folder. A strategy whose
  thresholds are module constants, as fees and notes, keeps the empty `NoParams`.
- **`minutes`.** The road minutes between every two places of the map, which the base class builds for each strategy.
- **`observe(event)`.** The one abstract method: learns from one event of the week. `Desk.handle` feeds every event
  to every strategy in `Desk.strategies`, in order, before the desk answers it. A strategy that learns nothing from
  events, as fees, says so in its `observe`.
- **`summary()`.** One line on the strategy's week, printed at the end of a practice week. Offers and bundling keep
  one; the others return an empty string and print nothing.

Each strategy then has its own methods for the desk's questions, such as `Admission.assess`, `PricingModel.price`,
`FeePlanner.schedule`, `Offers.due` or `Bundler.due`.

## A new strategy

1. Add a folder with a `README.md`, a module with a frozen `Params` dataclass and a subclass of `Strategy`, and an
   `__init__.py` that exports both.
2. Give the subclass the same constructor as the others, passing its default `Params()` on:

   ```python
   class MyStrategy(Strategy[Params]):
       def __init__(self, roster, world_map, level: int = 8, params: Params | None = None) -> None:
           super().__init__(roster, world_map, level, params or Params())

       def observe(self, event: DeskEvent) -> None: ...
   ```

3. Build it in `Desk.__init__` in `dispatch.py` and add it to `Desk.strategies`, so it sees every event.

## The play loop of `dispatch.py`

At the end of a practice week, `dispatch.py` prints two more lines. `Requests` counts the week's requests by route
(`advance`, `actions`, `score`, …). `Stops` gives the reason for each `advance`: the kind of event that stopped the
clock, `poll`, `midnight` or `end`. The request count sets how long a week takes: each request waits for the
network's round trip, about 175 ms through a Claude Code cloud proxy. To keep the count low, the loop does not stop
for every price request. The dealer decides at the request's `respondBy`, 15 minutes after the request, on our last
quote. So while requests keep coming, the loop looks for new ones at least every 14 minutes (`poll`) and quotes them
together with its answers to the other events. A quote sent anywhere before `respondBy` gets the same answer, so the
week stays the same. On the level 8 starter week in `data/` (`smoke-1`), this cuts the stops of the clock from 1,725 to
about 1,390.
