# Herding the competitor

A dispatch system built on [`strategies/headroom`](../headroom/README.md). The handbook says that each morning the
competitor cuts its prices for a dealer whose recent requests we mostly won, and raises them where we won few. This
system sometimes loses such a dealer's low-margin requests on purpose, rather than winning every car and inviting
the cut. Headroom and the other systems stay as they are.

| File          | Class          | Builds on         | What it decides                                             |
| ------------- | -------------- | ----------------- | ----------------------------------------------------------- |
| `pricing.py`  | `HerdPricing`  | `HeadroomPricing` | Which low-margin requests to lose, and every ordinary price |
| `dispatch.py` | `Desk`         | the headroom desk | The system, with every request registered for its outcome   |

`HerdPricing` is a subclass of `Strategy` through `HeadroomPricing`, with the constructor
`(roster, world_map, level=8, params=None)` and a frozen `Params`. No separate admission strategy is needed: pricing
receives admission's expected driver cost, and returning no normal price lets the ceiling desk release the request.

## Run it

From the repository root:

```sh
uv run strategies/herd_competitor/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `herd-competitor`. The `Herd` line at the end counts deliberate low-margin
declines and active-dealer requests kept by the margin guard.

## The strategy

1. **A rolling window per dealer.** The desk registers every request, including one admission declines. Each
   `order_won` or `order_lost` adds its result to that dealer's window of the last 20 decided requests. The win share
   is over however many outcomes are in the window so far.
2. **Two thresholds, with hysteresis.** A win share above 0.70 starts herding that dealer. Herding continues until
   the share falls under 0.50. Below that floor there is nothing special to do: if the competitor raises its prices
   where we win few, our next wins have more room. Between the two thresholds the previous state stays in force.
3. **Sacrifice only low expected margin.** While herding, pricing first builds the ordinary headroom quote. It
   subtracts admission's expected driver cost from that quote. If the expected euro margin is at most 50, the normal
   price is withheld and the ceiling desk sends its standard quote at ten times the list price: a costless decline,
   above the ordinary maximum. Selection is per request as it arrives; the guard keeps every request whose margin is
   above the threshold.
4. **Every other quote is unchanged.** Headroom still supplies its learned multiplier, moving maximum, driver-cost
   floor, dealer trust, outage and price-war rules. A deliberately lost outcome stays in the dealer's rolling share,
   but its withheld normal quote is removed from pricing's pending outcomes, so it moves neither the learned price
   nor the maximum. Up to level 3 there is no herding because every quote wins.

## The cost

A deliberate loss gives up a real order and its expected margin to protect possible future margins. The handbook says
the competitor moves only a few steps at most, so the protection is bounded too. The initial window, thresholds and
guard are assumptions, not tuned values; this system has not been played or benchmarked.

## The variables

`Params` in `pricing.py`, exported as `HerdParams`, extends `HeadroomParams` with:

| Variable       | Default | What it does                                                   |
| -------------- | ------- | -------------------------------------------------------------- |
| `herd_window`  | 20      | The decided requests in each dealer's rolling win-share window |
| `herd_ceiling` | 0.70    | A win share above this starts herding                          |
| `herd_floor`   | 0.50    | Herding stops when the win share falls under this              |
| `herd_keep`    | 50.0    | Euros of expected margin above which a request is never lost   |
