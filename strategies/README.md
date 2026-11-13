# Strategies

Each folder here is one strategy: one part of the decisions that `dispatch.py` makes. Every strategy is a subclass of
the abstract base class `Strategy` in [`strategy.py`](strategy.py), so they are all built, fed and read the same way.

| Folder                              | Class          | What it decides                                                 |
| ----------------------------------- | -------------- | --------------------------------------------------------------- |
| [`notes/`](notes/README.md)         | `NoteReader`   | What a dealer's note says, and the snow that a pickup waits for |
| [`admission/`](admission/README.md) | `Admission`    | Which price requests to take, and which option to quote         |
| [`pricing/`](pricing/README.md)     | `PricingModel` | The price of each quote, learned from our wins and losses       |
| [`fees/`](fees/README.md)           | `FeePlanner`   | The fee schedule of each gig                                    |
| [`offers/`](offers/README.md)       | `Offers`       | Direct offers to drivers near a gig's pickup                    |
| [`bundling/`](bundling/README.md)   | `Bundler`      | Which orders' cars go together in one gig                       |

Three folders are whole systems of their own: each holds a dispatcher plus its own strategies, so a week played
there is that system's, not `dispatch.py`'s. None of them changes the folders above.

| Folder                                      | Classes                                | What it is                                                |
| ------------------------------------------- | -------------------------------------- | --------------------------------------------------------- |
| [`baseline/`](baseline/README.md)           | `BaselineAdmission`, `BaselineFees`, … | The organisers' starter as strategies: our fixed baseline |
| [`price_ladder/`](price_ladder/README.md)   | `LadderPricing`, `ShadowAdmission`     | A clamped price ladder with a shadow price on capacity    |
| [`scarcity_cost/`](scarcity_cost/README.md) | `ScarcityAdmission`                    | Admission with the town's quotas per driver priced in     |

[`bench/`](bench/README.md) is not a strategy either: it compares versions of `dispatch.py` on the same seeds.

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
