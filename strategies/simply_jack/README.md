# Simply Jack

The simplest dispatch system we have: a few plain rules in one file, [`dispatch.py`](dispatch.py), with every number
as a named constant at its top. It is built so that anyone on the team can read it top to bottom, and then improved
one small step at a time: play a week, change one thing, play again, and keep the change only if the margin went up.
Issue #280.

Jack makes two decisions. Everything else (posting gigs, reading notes, retries after a failed visit, bundling, direct
offers, the final) is the root [`dispatch.py`](../../dispatch.py), unchanged.

## The rules

**1. The price.** For each price request:

- **Each dealer has its own price**, a factor on the list price. It starts at `PRICE` (1.55). A request of that dealer
  that we win raises it by `LADDER_UP` (2%); one that we lose lowers it by `LADDER_DOWN` (1%); it stays between
  `PRICE_MIN` (1.30) and `PRICE_MAX` (2.00). So Jack wins about a third of what he quotes, and a dealer who trusts us
  pays more.
- **Earn trust first.** In the first `TRUST_DAYS` (1: Monday) the two steps swap: a loss cuts 2% and a win adds
  1%. Jack wins most requests at a small margin then, to earn the dealers' trust (at level 8 each order on time
  lets a dealer accept 1% more from us), and takes the bigger margin later in the week.
- **Each morning** every dealer's price falls by `MORNING_STEP` (2%): overnight the competitor cuts its prices for the
  dealers we won most from.
- **Too few drivers.** Each car that got the deadline warning (no driver 3 hours before its last pickup) in the last
  24 hours adds `WARN_STEP` (2%) to every price, so Jack takes fewer cars while his drivers are behind.
- **The price war.** Once a week the competitor quotes 20% less for a day. When Jack wins at most one of his last
  `WAR_WINDOW` (15) quotes, he quotes `WAR_PRICE` (0.85) times his prices until 18:00, and the prices learn nothing
  that day. It comes once a week, never on the day after the trust days (when Jack's new prices lose a lot anyway),
  and the window counts every quote (step 76).
- **Leave out** every option that gives a driver less than `MIN_LEAD` (8 hours) to reach the car: the option's
  deadline, less the drive, less the minute the dealer decides.
- **Decline** when no option is left, when a car goes from or to a private address (its narrow booked slot made a
  quarter of those cars late), or when the typical driver fee is more than `MAX_FEE_LIST` (1.16) times the list
  price. A declined request gets a quote of ten times the list price, which loses at no cost.

**2. The driver fee.** For each gig: post it at `FEE_OPEN` (1.0) times the typical fee, then raise it in `FEE_STEPS`
(6) even steps to `FEE_TOP` (1.5) times the typical fee, which it reaches `TOP_BEFORE` (3 hours) before the car's
last pickup. Drivers plan their day in the morning, so when the top is due on a later day, the gig holds its opening
fee until `DAWN` (06:00) of that day, and only then climbs. With an hour or less to go, as after the deadline warning,
the gig goes at the top fee at once.

The prices start again at `PRICE` after a restart in the final: they learn only from the quotes this run sent.

## Run it

From the repository root, with the options of the root `dispatch.py` (`--level`, `--seed`, `--board`, `--final`):

```sh
uv run --env-file .env strategies/simply_jack/dispatch.py --level 8 --seed spread-9
```

Its weeks are saved like the root system's (`tools/record.py`), with the policy `simply-jack` and, in `meta.json`
under `settings`, the numbers the week was played with. At the end of a practice week it prints one line:

```text
Simply Jack: 342 won, 439 lost, 249 declined; dealer prices x1.35 to x1.83; price war on day 3, 169 war quotes. ...
```

## The steps

Every step is one practice week at level 8, played online after one change to the version before it. A change that
lowered the margin on its seed was undone before the next step ("Kept: no"). A week is ranked when at least 90% of
its orders arrive on time. Each week is saved under `data/scrape/runs/L8/<seed>/`.

Steps 1 to 48 were played on `spread-9`, the richest of our practice weeks. From step 49 the seed changes after every
five versions, so that Jack does not fit one week: the first week on each seed ("base") is the best version so far
as it is, and each later change is judged against it on that seed. For reference, `all_in` made €16,048 on
`spread-9`, €13,293 on `spread-4`, €13,592 on `spread-1`, €17,328 on `spread-19` and €17,012 on `spread-16`.

| Step | Seed      | Change                                                                           |  Margin | Orders |            On time | Kept |
| ---: | --------- | -------------------------------------------------------------------------------- | ------: | -----: | -----------------: | ---- |
|    1 | spread-9  | start                                                                            |  €8,617 |    483 | 88.4% (not ranked) | yes  |
|    2 | spread-9  | PRICE 1.40 → 1.55                                                                | €11,385 |    360 |              91.1% | yes  |
|    3 | spread-9  | PRICE 1.55 → 1.70                                                                | €11,503 |    242 |              95.5% | yes  |
|    4 | spread-9  | FEE_OPEN 1.0 → 0.8                                                               | €12,168 |    228 |              96.5% | yes  |
|    5 | spread-9  | FEE_OPEN 0.8 → 0.7                                                               |  €8,800 |    201 |              93.0% | no   |
|    6 | spread-9  | TRUST_SHARE 0 → 1.0                                                              | €10,793 |    168 |              97.6% | yes  |
|    7 | spread-9  | TRUST_SHARE back to 0, MIN_LEAD 6h                                               | €11,691 |    212 |              95.8% | yes  |
|    8 | spread-9  | PRICE 1.70 → 1.55 (with MIN_LEAD)                                                | €11,995 |    327 |              94.2% | yes  |
|    9 | spread-9  | fee holds until DAWN 06:00 of the last morning                                   | €13,194 |    318 |              91.5% | yes  |
|   10 | spread-9  | FEE_RESCUE 2.5                                                                   | €12,680 |    328 |              93.0% | no   |
|   11 | spread-9  | FEE_OPEN 0.8 → 0.9                                                               | €13,101 |    327 |              91.1% | no   |
|   12 | spread-9  | per-dealer price ladder (+2% a win, -1% a loss)                                  | €15,202 |    311 |              92.3% | yes  |
|   13 | spread-9  | LADDER_UP 0.02 → 0.03                                                            | €13,705 |    267 |              94.0% | no   |
|   14 | spread-9  | PRICE_MIN 1.40 → 1.50                                                            | €13,594 |    289 |              94.1% | no   |
|   15 | spread-9  | FEE_STEPS 6 → 11                                                                 | €14,734 |    309 |              93.9% | no   |
|   16 | spread-9  | LADDER_DOWN 0.01 → 0.015                                                         | €13,797 |    337 |              92.6% | no   |
|   17 | spread-9  | FEE_TOP 1.8 → 1.6                                                                | €15,294 |    310 |              91.9% | yes  |
|   18 | spread-9  | first raise at 06:00 sharp                                                       | €12,573 |    309 |              90.9% | no   |
|   19 | spread-9  | FEE_RESCUE 2.5 after the warning (unranked)                                      | €11,693 |    299 |              90.0% | no   |
|   20 | spread-9  | FEE_TOP 1.6 → 1.4 (equal)                                                        | €15,274 |    310 |              91.6% | no   |
|   21 | spread-9  | ladder per dealer and option kind                                                | €13,193 |    326 |              91.1% | no   |
|   22 | spread-9  | TOP_BEFORE 3h → 6h                                                               | €13,461 |    313 |              93.6% | no   |
|   23 | spread-9  | decline private addresses                                                        | €14,568 |    270 |              94.8% | yes  |
|   24 | spread-9  | LADDER_DOWN 0.01 → 0.015 (with private rule)                                     | €14,842 |    302 |              95.0% | yes  |
|   25 | spread-9  | LADDER_DOWN 0.015 → 0.02                                                         | €13,434 |    304 |              92.8% | no   |
|   26 | spread-9  | MAX_FEE_SHARE 0.75 → 0.85                                                        | €14,459 |    318 |              93.1% | no   |
|   27 | spread-9  | PRICE start 1.55 → 1.45                                                          | €14,397 |    331 |              92.7% | no   |
|   28 | spread-9  | PRICE_MAX 2.0 → 2.5                                                              | €14,866 |    295 |              92.5% | no   |
|   29 | spread-9  | HUB_PRICE 0.85 to Helsinki area                                                  | €12,941 |    313 |              91.4% | no   |
|   30 | spread-9  | REMOTE_PRICE 1.10 to places with <10 drivers                                     | €15,002 |    288 |              92.4% | no   |
|   31 | spread-9  | DIAGNOSTIC: root fee schedule with Jack prices (not a Jack version)              | €10,578 |    326 |              97.5% | no   |
|   32 | spread-9  | TRUST_DAYS 2: swapped ladder steps Mon-Tue (unranked)                            | €11,552 |    331 | 88.8% (not ranked) | yes  |
|   33 | spread-9  | TRUST_DAYS 1: swapped ladder steps on Monday only                                | €15,025 |    327 |              92.0% | yes  |
|   34 | spread-9  | HARVEST_DAY Thursday: losses stop lowering prices                                | €12,636 |    280 |              93.9% | no   |
|   35 | spread-9  | decline private addresses (on v33)                                               | €14,342 |    282 |              96.5% | yes  |
|   36 | spread-9  | TRUST_DAYS 1 → 2 (with private rule)                                             | €15,011 |    306 |              95.1% | yes  |
|   37 | spread-9  | LADDER_UP 0.02 → 0.03                                                            | €14,193 |    293 |              93.9% | no   |
|   38 | spread-9  | decline only private deliveries                                                  | €14,296 |    325 |              92.9% | no   |
|   39 | spread-9  | outage rule: 4 wins in a row from a place  →  x1.20                              | €14,153 |    299 |              93.6% | no   |
|   40 | spread-9  | price war rule: 12 losses in a row  →  x0.88 until 18:00                         | €15,166 |    305 |              95.4% | yes  |
|   41 | spread-9  | WAR_PRICE 0.88 → 0.80                                                            | €15,291 |    317 |              95.3% | yes  |
|   42 | spread-9  | MAX_FEE_LIST 1.16 x list instead of share of our price                           | €14,392 |    350 |              91.7% | no   |
|   43 | spread-9  | PRICE start 1.55 → 1.45 with trust days                                          | €14,369 |    336 |              93.2% | no   |
|   44 | spread-9  | ladder steps doubled to +4% / -2%                                                | €14,588 |    322 |              92.5% | no   |
|   45 | spread-9  | SAME_DAY_PRICE 1.10                                                              | €13,095 |    273 |              95.2% | no   |
|   46 | spread-9  | the war discount comes after the fee check; one war a week                       | €15,756 |    350 |              94.9% | yes  |
|   47 | spread-9  | WAR_PRICE 0.80 → 0.85                                                            | €15,999 |    333 |              95.5% | yes  |
|   48 | spread-9  | WAR_PRICE 0.85 → 0.90                                                            | €15,711 |    313 |              94.9% | no   |
|   49 | spread-4  | new seed: v47 as it is                                                           |  €9,812 |    296 | 85.1% (not ranked) | base |
|   50 | spread-4  | FEE_TOP 1.6 → 2.0                                                                |  €8,971 |    300 | 89.0% (not ranked) | yes  |
|   51 | spread-4  | WARN_STEP 2% per car warned in the last 24 hours                                 |  €9,892 |    247 |              90.7% | yes  |
|   52 | spread-4  | losses at prices lifted by warnings do not count toward the war                  |  €9,882 |    222 |              90.5% | yes  |
|   53 | spread-4  | FEE_OPEN 0.8 → 0.9                                                               |  €9,681 |    222 |              91.9% | no   |
|   54 | spread-1  | new seed: v52 as it is                                                           |  €9,378 |    272 |              93.8% | base |
|   55 | spread-1  | PRICE_MIN 1.40 → 1.25                                                            |  €7,593 |    273 |              91.2% | no   |
|   56 | spread-1  | WARN_STEP 0.02 → 0.01                                                            |  €9,877 |    290 |              93.4% | yes  |
|   57 | spread-1  | MAX_FEE_LIST 1.16 x list instead of MAX_FEE_SHARE                                | €10,219 |    296 |              93.6% | yes  |
|   58 | spread-1  | PRICE_MIN 1.40 → 1.30                                                            | €10,543 |    322 |              91.9% | yes  |
|   59 | spread-19 | new seed: v58 as it is                                                           | €12,549 |    317 |              91.8% | base |
|   60 | spread-19 | every loss counts toward the war again                                           | €12,051 |    318 |              91.2% | no   |
|   61 | spread-19 | FEE_TOP 2.0 → 1.6                                                                | €14,657 |    313 |              91.7% | yes  |
|   62 | spread-19 | every loss counts toward the war (unranked)                                      | €14,303 |    348 | 89.9% (not ranked) | no   |
|   63 | spread-19 | TRUST_DAYS 2 → 1                                                                 | €15,470 |    286 |              93.4% | yes  |
|   64 | spread-16 | new seed: v63 as it is (unranked)                                                | €13,505 |    280 | 88.9% (not ranked) | base |
|   65 | spread-16 | WARN_STEP 0.01 → 0.02 (unranked)                                                 | €13,168 |    262 | 89.3% (not ranked) | no   |
|   66 | spread-16 | FEE_OPEN 0.8 → 0.9                                                               | €14,902 |    301 |              91.7% | yes  |
|   67 | spread-16 | FEE_OPEN 0.9 → 1.0                                                               | €14,993 |    310 |              93.5% | yes  |
|   68 | spread-16 | FEE_TOP 1.6 → 1.5                                                                | €15,359 |    307 |              94.1% | yes  |
|   69 | spread-9  | new seed: v68 as it is                                                           | €16,365 |    345 |              97.4% | base |
|   70 | spread-9  | LADDER_DOWN 0.01 → 0.015                                                         | €14,665 |    328 |              98.5% | no   |
|   71 | spread-9  | TRUST_DAYS 1 → 2                                                                 | €15,834 |    346 |              98.0% | no   |
|   72 | spread-9  | WAR_LOSSES 12 → 10                                                               | €16,185 |    342 |              97.1% | no   |
|   73 | spread-9  | FEE_TOP 1.5 → 1.4                                                                | €15,641 |    316 |              97.5% | no   |
|   74 | spread-4  | new seed: v69 as it is                                                           | €11,070 |    246 |              92.3% | base |
|  74b | spread-4  | repeat of v74 (an edit failed; identical week)                                   | €11,070 |    246 |              92.3% | no   |
|   75 | spread-4  | war = at most 1 win in the last 15 quotes (same week: no war seen)               | €11,070 |    246 |              92.3% | yes  |
|   76 | spread-4  | the war window counts every quote                                                | €11,530 |    296 |              91.2% | yes  |
|   77 | spread-4  | a war can come every day (+€37 but 90.2% on time)                                | €11,567 |    316 |              90.2% | no   |
|   78 | spread-4  | MIN_LEAD 6h → 8h                                                                 | €12,023 |    291 |              92.8% | yes  |
|   79 | spread-1  | new seed: v78 as it is                                                           |  €9,675 |    301 |              95.0% | base |
|   80 | spread-1  | MORNING_STEP 3% each morning                                                     |  €9,857 |    330 |              94.8% | yes  |
|   81 | spread-1  | TRUST_DAYS 1 → 2                                                                 | €10,127 |    361 |              93.4% | yes  |
|   82 | spread-1  | PRICE start 1.55 → 1.50                                                          | €10,171 |    379 |              93.4% | yes  |
|   83 | spread-1  | MORNING_STEP 0.03 → 0.05                                                         | €10,461 |    394 |              92.6% | yes  |
|   84 | spread-19 | new seed: v83 as it is                                                           | €14,727 |    409 |              93.6% | base |
|   85 | spread-19 | MORNING_STEP 0.05 → 0.02                                                         | €14,917 |    380 |              95.8% | yes  |
|   86 | spread-19 | TRUST_DAYS 2 → 1 (equal)                                                         | €14,902 |    355 |              96.3% | no   |
|   87 | spread-19 | FEE_OPEN 1.0 → 0.9                                                               | €15,318 |    370 |              92.2% | yes  |
|   88 | spread-19 | LADDER_UP 0.02 → 0.025                                                           | €13,940 |    359 |              91.4% | no   |
|   89 | spread-16 | new seed: v87 as it is (unranked)                                                | €13,767 |    389 | 86.1% (not ranked) | base |
|   90 | spread-16 | WARN_STEP 0.01 → 0.02 (unranked)                                                 | €14,226 |    341 | 87.1% (not ranked) | yes  |
|   91 | spread-16 | TRUST_DAYS 2 → 1 (unranked)                                                      | €14,580 |    319 | 88.7% (not ranked) | yes  |
|   92 | spread-16 | FEE_OPEN 0.9 → 1.0 (ranked again)                                                | €13,987 |    300 |              91.0% | yes  |
|   93 | spread-16 | PRICE start 1.50 → 1.55 (+€93 but 90.1% on time)                                 | €14,080 |    322 |              90.1% | no   |
|   95 | spread-9  | private pickups while no car is warned                                           | €15,310 |    370 |              97.0% | no   |
|   96 | spread-9  | outage rule again (its lifted losses set off the war window)                     | €13,874 |    339 |              96.5% | no   |
|   97 | spread-9  | WARN_STEP 0.02 → 0.01                                                            | €16,239 |    388 |              96.6% | yes  |
|   98 | spread-9  | FEE_OPEN 1.0 → 1.1                                                               | €13,488 |    386 |              97.2% | no   |
|   99 | spread-4  | new seed: v97 as it is (unranked)                                                | €10,821 |    303 | 89.4% (not ranked) | base |
|  100 | spread-4  | WARN_STEP 0.01 → 0.02 (ranked again)                                             | €10,504 |    274 |              90.9% | yes  |
|  101 | spread-4  | MORNING_STEP 0.02 → 0                                                            | €10,171 |    247 |              90.3% | no   |
|  102 | spread-4  | no war on the day after the trust days (same week here; guards steps 92 and 101) | €10,504 |    274 |              90.9% | yes  |
|  103 | spread-4  | PRICE start 1.50 → 1.55                                                          | €11,348 |    280 |              91.4% | yes  |

What the steps taught:

- **The price and the trust carry the margin.** A fixed price (steps 1 to 8) stalled near €12,000 on `spread-9`; a
  price for each dealer that moves with its wins and losses (step 12) added €2,000 at once.
- **Drivers plan their day in the morning.** Holding the fee until 06:00 of the pickup day (step 9) cut the driver
  bill by about a tenth. Jack's fee rule paid far less than the root system's schedule (step 31, a check only).
- **Steep raises teach drivers to wait.** A rescue fee of 2.5 times the typical fee after the deadline warning (steps
  10 and 19) made more cars late, not fewer: drivers learn the ratio of the fee they book to the first fee they saw.
  A flatter climb, from 1.0 to 1.5, won on three seeds (steps 61, 66 to 68).
- **One seed misleads.** The version tuned on `spread-9` (step 47) was not ranked on `spread-4` (step 49): that week
  has fewer drivers. The rule for too few drivers (step 51) made it ranked, and the versions tuned on five seeds made
  more on `spread-9` too (step 69: €16,365 against €15,999).
- **The price war is worth a rule**, and so is seeing it reliably: on the war day the other systems quote about 1.45
  times the list price and win three times as many cars as Jack did at 1.58 (step 40). A war that the rule missed
  cost about €1,000 (steps 70, 71, 73).
- **Rules that lift the price confuse the price war.** Losses at prices that the outage rule (step 96) or the
  warnings lifted look like the war, and a war seen on the wrong day costs the real one (steps 92, 95, 96).
- **Seeds pull the numbers apart.** A weak brake on warnings and more volume suit `spread-9`, where drivers are many,
  and leave `spread-4` and `spread-16` unranked (steps 89, 99). A ranked week beats an unranked one, so the brake
  stays at 2%.
- **One week is noisy.** A small change moves what every driver does for the rest of the week, so two versions that
  differ by a few hundred euros are within the noise of one week. Step 77 was undone although it made €37 more: it
  left the week at 90.2% on time, a few cars from not being ranked.
