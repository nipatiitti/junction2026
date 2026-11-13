# Ladder pricing and a capacity shadow price

A folder that builds on the shared strategies, the way [`../baseline/`](../baseline/README.md) and
`strategies/ceiling/` do: its own copy of the root `dispatch.py` that quotes and admits with the two strategies
below. The root `dispatch.py` and the strategies it builds stay as they are. Issue #126.

| File           | What it holds                                                                                         |
| -------------- | ----------------------------------------------------------------------------------------------------- |
| `dispatch.py`  | A copy of the root `dispatch.py` that quotes and admits with the two strategies below                 |
| `pricing.py`   | `LadderPricing`: the adaptive quoting of `strategies/pricing`, with a ladder for its world multiplier |
| `admission.py` | `ShadowAdmission`: the admission control of `strategies/admission`, with a shadow price on capacity   |

Each is a subclass of `Strategy` ([`../strategy.py`](../strategy.py)) with the usual constructor, `observe` and
`summary`, so the desk builds and feeds them like its own.

## Run it

From the repository root, like the root `dispatch.py`:

```sh
uv run strategies/price_ladder/dispatch.py --level 8 --seed spread-1                       # a practice week
uv run python -m strategies.bench strategies/price_ladder/dispatch.py dispatch.py --jobs 4 # against the root system
```

Its weeks are saved like the root system's (`record.py`), with the policy `price-ladder` instead of `dispatch`, so
they form their own group in `out/spread.sqlite` and `summary.json`.

## The ladder

`LadderPricing` is the adaptive quoting with a different rule for its world multiplier: one position on the list
price for the whole week, shared by every request. Each request gets essentially one final quote, so a per-lane state
would only add noise. It starts at the top of its range and every outcome moves it:

- a quote we lost drops it by 3%, a quote we won raises it by 1%;
- it never leaves `[floor, ceiling]`, the default 1.0 to 1.5 × list;
- the unequal steps settle it where the wins balance the losses: `loss_step / (win_step + loss_step)` of the quotes
  win, 75% with the default steps. A cheaper competitor walks it to the floor, a dearer one to the top.

Its `Params` holds the range and the steps. The price war, the outage and dealer trust work as in the adaptive model;
the per-lane offsets do not. `summary()` prints where the ladder ended the week and how often it sat at either end of
its range.

On the saved level-8 weeks the win curve falls from about 56% at 1.0 × list to 47% at 1.5 × list, so a 75% target
sits below the market: expect the ladder to spend much of the week near its floor, trading margin for more orders.

## The shadow price

`ShadowAdmission` splits a request's cost into a `Cost(fee, hours, shadow)`:

- `fee` is the base's expected driver fee. It reads the typical fee and the driver list, never the list price, our
  quote or the won price: what drivers need does not depend on what we charge.
- `hours` are the drive minutes of the request's cars.
- `shadow` is notional. The area day's load over its capacity is `u = (load + this car) / capacity`, the same ratio
  as the base's capacity gate. The shadow is
  `kappa × max(0, u - start) / max(eps, 1 - u) × hours`: zero while the area is under `start` full, rising as it
  fills. It is the opportunity cost of the orders the committed driver hours crowd out.
- The profit check compares the quote against `fee + shadow`, so a request in a filling area must pay more to be
  taken. Its `Params(kappa=0)` turns the shadow off and leaves the base's behaviour.

The shadow is never paid to a driver: it does not reach `strategies/fees`, and no posted fee includes it.

`kappa` (cents per driver hour) is a placeholder to tune on the bench: the saved weeks pay about €32.58 an hour of
driving, so the default €20 an hour is a fraction of that.
