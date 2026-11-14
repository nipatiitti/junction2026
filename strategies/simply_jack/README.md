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
  `PRICE_MIN` and `PRICE_MAX`. So Jack wins about a third of what he quotes, and a dealer who trusts us pays more.
- **Earn trust early.** In the first `TRUST_DAYS` (Monday and Tuesday) the two steps swap: a loss cuts 2% and a win
  adds 1%. Jack wins most requests at a small margin then, to earn the dealers' trust (at level 8 each order on time
  lets a dealer accept 1% more from us), and takes the bigger margin later in the week.
- **The price war.** Once a week the competitor quotes 20% less for a day. When Jack loses `WAR_LOSSES` (12) requests
  in a row from Tuesday on, he quotes `WAR_PRICE` (0.80) times his prices until 18:00, and the ladder learns nothing
  from that day.
- **Leave out** every option that gives a driver less than `MIN_LEAD` (6 hours) to reach the car: the option's
  deadline, less the drive, less the minute the dealer decides.
- **Decline** when no option is left, when a car goes from or to a private address (its narrow booked slot made a
  quarter of those cars late), or when the typical driver fee is more than `MAX_FEE_SHARE` (75%) of our price. A
  declined request gets a quote of ten times the list price, which loses at no cost.

**2. The driver fee.** For each gig: post it at `FEE_OPEN` (0.8) times the typical fee, then raise it in `FEE_STEPS`
(6) even steps to `FEE_TOP` (1.6) times the typical fee, which it reaches `TOP_BEFORE` (3 hours) before the car's
last pickup. Drivers plan their day in the morning, so when the top is due on a later day, the gig holds its opening
fee until `DAWN` (06:00) of that day, and only then climbs. With an hour or less to go, as after the deadline warning,
the gig goes at the top fee at once.

The ladder starts again at `PRICE` after a restart in the final: it learns only from the quotes this run sent.

## Run it

From the repository root, with the options of the root `dispatch.py` (`--level`, `--seed`, `--board`, `--final`):

```sh
uv run --env-file .env strategies/simply_jack/dispatch.py --level 8 --seed spread-9
```

Its weeks are saved like the root system's (`tools/record.py`), with the policy `simply-jack` and, in `meta.json`
under `settings`, the numbers the week was played with. At the end of a practice week it prints one line:

```text
Simply Jack: 319 won, 383 lost, 328 declined; dealer prices x1.40 to x1.85; price war on day 3, 171 war quotes. ...
```

## The steps

Every step is one practice week at level 8 on the seed `spread-9`, played online after one change to the version
before it. A change that lowered the margin was undone before the next step ("Kept: no"). A week is ranked when at
least 90% of its orders arrive on time. Each week is saved under `data/scrape/runs/L8/spread-9/`.

`spread-9` is the richest of our practice weeks: the root `dispatch.py` made €13,716 there and `all_in` €16,048, and
the only system that passed €20,000 there (`ts-recall`) remembers each request's price from earlier weeks of the same
seed. So these numbers are higher than on `spread-1`, and they are tuned to this one week.

| Step | Change                                                              |  Margin | Orders |            On time | Kept |
| ---: | ------------------------------------------------------------------- | ------: | -----: | -----------------: | ---- |
|    1 | start                                                               |  €8,617 |    483 | 88.4% (not ranked) | yes  |
|    2 | PRICE 1.40 → 1.55                                                   | €11,385 |    360 |              91.1% | yes  |
|    3 | PRICE 1.55 → 1.70                                                   | €11,503 |    242 |              95.5% | yes  |
|    4 | FEE_OPEN 1.0 → 0.8                                                  | €12,168 |    228 |              96.5% | yes  |
|    5 | FEE_OPEN 0.8 → 0.7                                                  |  €8,800 |    201 |              93.0% | no   |
|    6 | TRUST_SHARE 0 → 1.0                                                 | €10,793 |    168 |              97.6% | yes  |
|    7 | TRUST_SHARE back to 0, MIN_LEAD 6h                                  | €11,691 |    212 |              95.8% | yes  |
|    8 | PRICE 1.70 → 1.55 (with MIN_LEAD)                                   | €11,995 |    327 |              94.2% | yes  |
|    9 | fee holds until DAWN 06:00 of the last morning                      | €13,194 |    318 |              91.5% | yes  |
|   10 | FEE_RESCUE 2.5                                                      | €12,680 |    328 |              93.0% | no   |
|   11 | FEE_OPEN 0.8 → 0.9                                                  | €13,101 |    327 |              91.1% | no   |
|   12 | per-dealer price ladder (+2% a win, -1% a loss)                     | €15,202 |    311 |              92.3% | yes  |
|   13 | LADDER_UP 0.02 → 0.03                                               | €13,705 |    267 |              94.0% | no   |
|   14 | PRICE_MIN 1.40 → 1.50                                               | €13,594 |    289 |              94.1% | no   |
|   15 | FEE_STEPS 6 → 11                                                    | €14,734 |    309 |              93.9% | no   |
|   16 | LADDER_DOWN 0.01 → 0.015                                            | €13,797 |    337 |              92.6% | no   |
|   17 | FEE_TOP 1.8 → 1.6                                                   | €15,294 |    310 |              91.9% | yes  |
|   18 | first raise at 06:00 sharp                                          | €12,573 |    309 |              90.9% | no   |
|   19 | FEE_RESCUE 2.5 after the warning (unranked)                         | €11,693 |    299 | 90.0% (not ranked) | no   |
|   20 | FEE_TOP 1.6 → 1.4 (equal)                                           | €15,274 |    310 |              91.6% | no   |
|   21 | ladder per dealer and option kind                                   | €13,193 |    326 |              91.1% | no   |
|   22 | TOP_BEFORE 3h → 6h                                                  | €13,461 |    313 |              93.6% | no   |
|   23 | decline private addresses                                           | €14,568 |    270 |              94.8% | yes  |
|   24 | LADDER_DOWN 0.01 → 0.015 (with private rule)                        | €14,842 |    302 |              95.0% | yes  |
|   25 | LADDER_DOWN 0.015 → 0.02                                            | €13,434 |    304 |              92.8% | no   |
|   26 | MAX_FEE_SHARE 0.75 → 0.85                                           | €14,459 |    318 |              93.1% | no   |
|   27 | PRICE start 1.55 → 1.45                                             | €14,397 |    331 |              92.7% | no   |
|   28 | PRICE_MAX 2.0 → 2.5                                                 | €14,866 |    295 |              92.5% | no   |
|   29 | HUB_PRICE 0.85 to Helsinki area                                     | €12,941 |    313 |              91.4% | no   |
|   30 | REMOTE_PRICE 1.10 to places with <10 drivers                        | €15,002 |    288 |              92.4% | no   |
|   31 | DIAGNOSTIC: root fee schedule with Jack prices (not a Jack version) | €10,578 |    326 |              97.5% | no   |
|   32 | TRUST_DAYS 2: swapped ladder steps Mon-Tue (unranked)               | €11,552 |    331 | 88.8% (not ranked) | yes  |
|   33 | TRUST_DAYS 1: swapped ladder steps on Monday only                   | €15,025 |    327 |              92.0% | yes  |
|   34 | HARVEST_DAY Thursday: losses stop lowering prices                   | €12,636 |    280 |              93.9% | no   |
|   35 | decline private addresses (on v33)                                  | €14,342 |    282 |              96.5% | yes  |
|   36 | TRUST_DAYS 1 → 2 (with private rule)                                | €15,011 |    306 |              95.1% | yes  |
|   37 | LADDER_UP 0.02 → 0.03                                               | €14,193 |    293 |              93.9% | no   |
|   38 | decline only private deliveries                                     | €14,296 |    325 |              92.9% | no   |
|   39 | outage rule: 4 wins in a row from a place  →  x1.20                 | €14,153 |    299 |              93.6% | no   |
|   40 | price war rule: 12 losses in a row  →  x0.88 until 18:00            | €15,166 |    305 |              95.4% | yes  |
|   41 | WAR_PRICE 0.88 → 0.80                                               | €15,291 |    317 |              95.3% | yes  |
|   42 | MAX_FEE_LIST 1.16 x list instead of share of our price              | €14,392 |    350 |              91.7% | no   |
|   43 | PRICE start 1.55 → 1.45 with trust days                             | €14,369 |    336 |              93.2% | no   |
|   44 | ladder steps doubled to +4% / -2%                                   | €14,588 |    322 |              92.5% | no   |

What the steps taught:

- **The price and the trust carry the margin.** A fixed price (steps 1 to 8) stalled near €12,000; a price for each
  dealer that moves with its wins and losses (step 12) added €2,000 at once.
- **Drivers plan their day in the morning.** Holding the fee until 06:00 of the pickup day (step 9) cut the driver
  bill by about a tenth.
- **Steep raises teach drivers to wait.** A rescue fee of 2.5 times the typical fee after the deadline warning (steps
  10 and 19) made more cars late, not fewer: drivers learn the ratio of the fee they book to the first fee they saw.
- **One week is noisy.** A small change moves what every driver does for the rest of the week, so two versions that
  differ by a few hundred euros are within the noise of one week. Steps 36 and 41 are kept for their on-time share
  (95%, against 92% in step 17) at the same margin.
- **The price war is worth a rule.** On the war day the other systems quote about 1.45 times the list price and win
  three times as many cars as Jack did at 1.58 (step 40).
