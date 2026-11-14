# Option menu

A dispatch system built on [`strategies/ceiling`](../ceiling/README.md): its `Desk` is a subclass of the ceiling
desk that quotes admission's option and every slower one. Issue #187. Ceiling and the root system stay as they are.

| File          | Class        | Builds on        | What it decides                                          |
| ------------- | ------------ | ---------------- | -------------------------------------------------------- |
| `menu.py`     | `OptionMenu` | `Strategy`       | Which options go on a quote, and the slower ones' prices |
| `dispatch.py` | `Desk`       | the ceiling desk | The system: the ceiling desk's quote with the menu       |

## Run it

From the repository root:

```sh
uv run strategies/option_menu/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/option_menu/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `option-menu`. The `Option menu` line at the end of a week counts the quotes with
slower options, and how many won orders took admission's pick or a slower option.

## The strategy

Admission (`strategies/admission`) quotes one option: the earliest that leaves comfortable time for the drive, which
is the dearest one that fits. On the saved `ceiling` weeks every won order was `same_day` or `next_day`: ceiling never
quoted `within_3_days`. A dealer who would rather wait than pay for speed has nothing cheaper from us, and takes the
competitor's price.

1. **The menu.** The quote carries admission's option and every option of the request with a later deadline, at most
   `most` = 3. A later option leaves more time, so it is never harder to deliver on time than the pick.
2. **The prices.** Each option gets ceiling pricing's price for its own list price, which is lower for a later
   deadline: on the saved weeks `next_day` lists at 0.93 × `same_day`, and `within_3_days` at 0.93 × `next_day`.
   `slow_discount` (0 by default) takes a further share off for each step slower, never under the driver cost floor.
3. **The dealer chooses.** The dealer compares each option's price with the value of its speed, then with the
   competitor. A dealer who values speed takes the pick as before; one who does not can take a slower option from us.

## Offline replay

`analysis.replay`'s quote replay with this desk on the ten distinct saved `ceiling` weeks. Admission does not
change: 65.4% of the requests are taken, and 3,231 of ceiling's 3,233 won orders are kept. The weeks quoted one
option, so a quote with more options has an unknown answer more often (2,344 against 2,040). The bench below
measures which options the dealers take.

## Bench

To be played.
