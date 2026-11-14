# Flu guard

A dispatch system built on [`strategies/soft_top`](../soft_top/README.md): its `Desk` is a subclass of the soft-top
desk whose admission guards against the week's flu day. Issue #200. The systems it builds on stay as they are.

| File           | Class               | Builds on           | What it decides                                              |
| -------------- | ------------------- | ------------------- | ------------------------------------------------------------ |
| `admission.py` | `FluGuardAdmission` | `LaneCostAdmission` | Which options stay off a quote while the flu day is a risk   |
| `dispatch.py`  | `Desk`              | the soft-top desk   | The system: the soft-top desk with the admission above       |

`FluGuardAdmission` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through
`LaneCostAdmission`, with the constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/flu_guard/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/flu_guard/dispatch.py strategies/soft_top/dispatch.py --jobs 2
```

Its weeks are saved with the policy `flu-guard`. The `Flu guard` line at the end of a week says on which day the flu
showed, and how many options the guard kept off a quote.

## What the saved weeks show

At levels 7 and 8 every week has the flu: on one day, 30% of the drivers who meant to work stay at home (the
handbook). Nobody announces it. The 22 weeks of `soft_top` on `spread-1` to `spread-22` show how it arrives and what
it costs:

- **It shows a minute after midnight.** The drivers who are ill give their bookings for that day back in the first
  hour of the day. An usual night has none to two such drops. In 18 of the 22 weeks one night had 7 to 23 of them:
  on a Tuesday in 4 weeks, a Wednesday in 5, a Thursday in 3 and a Friday in 6.
- **A flu on Friday costs most.** A car that misses a Friday deadline waits for Monday. The six weeks with the flu on
  Friday delivered 88.5% to 96.8% of their orders on time, against 95.2% to 99.7% for the other sixteen. On
  `spread-21` the Friday had 101 orders due, 20 bookings given back at midnight and 13 more during the day; drivers
  took 59 gigs that day, 24 of them after 18:00, and 23 of the orders due that day were late, most by a weekend.
  The week ended at 88.5% on time: under the delivery minimum, so not ranked.
- **Friday is the fullest day.** Thursday is the busiest day for requests, and most of its cars are due on Friday:
  47 to 116 orders, more than on any earlier day in 18 of the 22 weeks.

A higher fee does not help on that day: there are fewer drivers, whatever they are paid. What helps is to owe fewer
cars on it.

## The strategy

1. **The flu day.** Admission counts the bookings given back in the first hour of each day (`night`). Five or more
   (`storm`) is the flu day.
2. **Friday, while the flu has not shown.** On Thursday and Friday, as long as no flu day has shown this week,
   Friday is likely to be it (6 of the 10 weeks in which it had not shown by Thursday). An option due on Friday
   then stays off the quote once Friday holds as many orders as the week's busiest earlier day (`friday_share` × the
   most orders due on one day before Friday, and at least `friday_least`). The quotes that wait for a dealer's
   answer count too. The request can still be quoted for another option, or it is declined.
3. **The flu day itself.** On the day it shows, no option due the same day is quoted.

Up to level 6 the flu comes only in some weeks, and the guard is off.

## The variables

`Params` in `admission.py`, exported as `FluGuardParams`, next to those of `strategies/lead_cost`.

| Variable       | Default | What it does                                                               |
| -------------- | ------- | -------------------------------------------------------------------------- |
| `night`        | 1 hour  | Bookings given back within this of midnight are the flu's                  |
| `storm`        | 5       | This many of them in one night is the flu day                              |
| `friday_share` | 1.0     | Friday holds this share of the week's busiest earlier day, until it shows  |
| `friday_least` | 40      | Friday always holds at least this many orders                              |
