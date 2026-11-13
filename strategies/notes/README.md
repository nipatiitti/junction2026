# Note reader

Reads a dealer's note, in Finnish, Swedish or English, into facts, and turns them into the stop windows,
audience and plates of a gig. Most failed visits come from a note the gig did not follow (HANDBOOK.md,
"Notes change what happens"); RULES.md, "Notes and changes of plan", says how notes are written.

- `notes.py`: `NoteReader`, the strategy (`strategies/README.md`): `read(request)` reads a request's note once, and
  `observe` keeps the snowfalls of each `forecast` event, which `pickup_window` waits for.
- `reader.py`: `read_note(text, arrived_at)` gives a `NoteFacts`, or `NO_FACTS` for a note that states none.
- `plan.py`: `pickup_window` and `delivery_window` turn the facts into stop windows.
- `check.py`: measures the reader on reveals, next to the starter's reader.

## The facts

| Fact                                                     | Field            | What `dispatch.py` does with it                                                                                  |
| -------------------------------------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------------------- |
| Car ready later                                          | `ready_at`       | The pickup window starts then.                                                                                   |
| Handed over after payment (a `release` event comes then) | `released_at`    | The pickup window starts then.                                                                                   |
| Real pickup hours                                        | `pickup_hours`   | The pickup window is one day inside them, ending an hour before closing: the first day with an hour left.        |
| Real delivery hours                                      | `delivery_hours` | The delivery window ends an hour before the real closing time on its last day.                                   |
| Tighter deadline                                         | `deadline`       | The delivery window ends then. A request whose note deadline passes before the car can be collected is declined. |
| Manual gearbox                                           | `manual`         | The gig's audience needs a manual licence.                                                                       |
| No plates                                                | `plates`         | The pickup goes `withPlates`.                                                                                    |
| Summer tyres                                             | `summer_tyres`   | The pickup window starts after any forecast snow at either end.                                                  |

A note speaks of the first car: in a trade-in, the new car. The reveals agree: the second car never carries a
note's fact. When a gig expires, the starter posts its cars again without stop windows; the pickup keeps the
window that the note still needs from then on (`Desk.noted_pickup`). A one-day window inside real hours
follows the driver: they plan by the stated hours, so a longer window could bring them after the real closing.
The hour before closing covers drives that run longer than the road minutes: a site is closed from its closing
minute on.

## Phrasings it reads

- **Days**: "tänään", "idag", "today"; "huomenna", "i morgon", "imorgon", "tomorrow", "tmrw"; "ylihuomenna",
  "i övermorgon", "the day after tomorrow". Weekday names and short forms ("to.", "pe", "Thurs", "fre") are 2 to
  6 days after the request. "ma-pe" and "Mon–Fri" in opening hours are not a day.
- **Times**: "klo 15", "kl. 15.30", "kello 1800", "14:30", "2:30 pm", "9am", "9:stä", "noon". An hour in words is
  a working hour, 9 to 17: "viideltä", "kolmesta", "neljään mennessä", "kahdentoista jälkeen", "klockan tre",
  "at two", "half three" and "puoli neljältä" (half an hour before: 14:30, 15:30).
- **Corrections and denials**: "ei kun", "eikun", "korjaus:", "correction:", "sorry, I mean", "rättelse:",
  "nej förlåt" replace the time or the day they name; "(not 15:00)", "ei klo 9", "inte kl 10" do not count.
- **Pickup**: "valmis vasta", "voi noutaa … alkaen", "noudettavissa aikaisintaan", "not ready before",
  "ready for pickup from", "klar först", "kan hämtas … och framåt"; after payment: "maksun jälkeen",
  "ostaja maksaa ensin", "luovutetaan kun maksu näkyy", "released after payment", "lämnas ut efter betalning".
- **Hours**: ranges ("nouto arkisin klo 7 - 14.30", "open weekdays 10:00-14:30", "Öppet vardagar 10-16.30",
  "8:sta 20:een") and closing times ("nouto ennen klo 15", "liike kiinni klo 16", "we close at 15:30",
  "täällä ei ketään 15.30 jälkeen", "kello 19 jälkeen ei enää luovutuksia"). Words like "kohde", "vastaanotto",
  "destination", "receiving" and "mottagaren" put them at the delivery site, the rest at the pickup.
- **Deadline**: "perillä … mennessä", "oltava perillä viimeistään", "toimitus perille viim.", "at destination …
  latest", "must be at destination by", "latest arrival", "framme senast", "ska vara på plats senast".
- **Car**: "manuaali", "manuaalivaihteinen", "käsivaihteinen", "manual", "stick shift", "manuell" (not "not a
  manual"); "kilvet puuttuu", "ei rekkareita", "rekisterikilvet irrotettu", "no plates", "unregistered",
  "saknar skyltar"; "kesärenkaat alla", "vielä kesärenkailla", "still on summer tyres", "sommardäck på" (not a
  spare set "takakontissa" or "in the boot").
- **Typos**: a word one letter off a word it knows ("huomennna", "toomorrow", "akisin", "Pltaes").

## What it does not read

- A private seller's or owner's slot ("myyjä kotona 7-10", "owner at home"): the request's window already is it.
- A day without a time ("valmis huomenna"), and times relative to now ("in two hours").
- Saturday hours from a note: the reveals show notes change only the weekday hours.
- Hours in words in English or Swedish without a cue word before them ("at", "by", "klockan", "half").

## Measure it on reveals

Play a week, write it to CSV and run the check on one or more folders:

```bash
uv run spread-reveal-csv <world id>
```

```bash
uv run python -m strategies.notes.check reveal-<world id> reveal-<world id>
```

`--misses "<fact>"` lists the notes where the reader gets that fact wrong. Each won car with a note counts once,
even when a seed was played twice. A fact counts as read when the reader's value equals the truth: the ready or
release time, the weekday hours (the stated ones when the note says nothing), the note's deadline (the world
keeps it only when it is before the request's latest deadline), and the three car facts. The starter's reader
gives only windows, so the check reads its pickup start as the earliest pickup, its earlier pickup end as the
closing time, and its earlier delivery end as both the closing time and the deadline.

## Latest results

13 November, level 8. Agreement with the reveal's truth on won cars with a note.

On `spread-4`, a week the reader was not tuned on (before three fixes it led to):

| Fact            | Notes | Changed by the note | Starter agrees | Reader agrees |
| --------------- | ----: | ------------------: | -------------: | ------------: |
| earliest pickup |   395 |                  30 |          93.9% |         99.5% |
| pickup hours    |   352 |                  20 |          95.5% |         99.7% |
| delivery hours  |   375 |                  14 |          90.9% |        100.0% |
| deadline        |   395 |                  30 |          87.8% |         99.7% |
| manual gearbox  |   395 |                   8 |          98.0% |        100.0% |
| no plates       |   395 |                  11 |          97.2% |        100.0% |
| summer tyres    |   395 |                   3 |          99.2% |        100.0% |

On the 17 team weeks it was tuned on (2,414 won cars with a note), the reader now agrees on every fact of every
note; the starter agrees on 90.8% (deadline) to 98.9% (summer tyres).

Failed visits (`visit_failed`) at level 8, starter against this reader:

| Seed       | Starter | Reader | Margin, starter | Margin, reader |
| ---------- | ------: | -----: | --------------: | -------------: |
| `spread-1` |      26 |      0 |     −€72,612.51 |    −€66,127.10 |
| `spread-2` |      32 |      1 |     −€46,907.28 |    −€44,852.60 |

These two weeks ran before windows inside real hours ended an hour before closing; the one failure left was a
driver who came at the closing minute. `spread-3` to `spread-5` are not measured yet.
