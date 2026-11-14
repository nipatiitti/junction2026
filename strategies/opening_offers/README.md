# Opening offers

A dispatch system built on the root [`dispatch.py`](../../dispatch.py): its `Desk` replaces `Offers` with
`OpeningOffers`, which also offers open gigs to drivers who live near the pickup. Issue #229. The root
dispatcher and `strategies/offers` stay as they are.

| File          | Class           | Builds on       | What it decides                         |
| ------------- | --------------- | --------------- | --------------------------------------- |
| `offers.py`   | `OpeningOffers` | `Offers`        | Which nearby drivers get a direct offer |
| `dispatch.py` | `Desk`          | the root `Desk` | The system: swaps in the offers above   |

## Run it

From the repository root:

```sh
uv run strategies/opening_offers/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/opening_offers/dispatch.py dispatch.py --jobs 2
```

Its weeks are saved with the policy `opening-offers`.

## The idea

`Offers` normally reaches only drivers finishing one of our gigs near a pickup, except for a rescue near the
pickup deadline, when it also asks drivers who live nearby. A driver who lives nearby but never opened the app
notification may therefore never get a direct offer.

`OpeningOffers` always uses the rescue's wider candidate list, but keeps the normal **chain offer fee** of 0.85
of the app fee for a non-rescue gig. At the deadline it uses the rescue fee as before. The usual guards stay in
place: eligible licence and rating, at most three offers per gig at once, at most three per driver in 24 hours,
no offers to a driver who already declined or dropped today, and none at night.

Useful question to measure: whether the wider offers replace bookings at a raised app fee with bookings at the
0.85 chain fee, rather than simply convincing drivers who would have booked the app gig anyway.

No scheduled changes to admission, pricing or fee schedules are made by this scenario.
