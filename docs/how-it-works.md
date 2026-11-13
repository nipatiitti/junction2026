# How it works (short)

Condensed from [/how](https://spread.bahnexpress.com/how), the plain-words page
for people. Exact numbers live in [rules.md](rules.md).

## The world

- One simulated week, Monday to the next Monday (runs on to Wednesday 22:00).
  ~1,000 price requests, Mon 08:00 – Fri 18:00.
- 30 towns from Helsinki to Rovaniemi, real drive times (Helsinki–Tampere ~2 h,
  Helsinki–Oulu ~6.5 h).
- Each week draws its own drivers and prices.

## Dealers, prices and the competitor

- A request: one car (or two for a trade-in, one price), up to three options
  (same day / next business day / within 3 business days), each with a deadline
  and list price, plus a typical driver fee. 15 minutes to answer.
- A competitor quotes on every request. The dealer weighs your price against
  its price and the value of the option's speed.
- Competitor ≈ list price up to level 6; about +25% at level 7 and +40% at
  level 8. It varies by lane and day, changes during the week, and cuts prices
  for dealers where you win most orders. You never see its prices — learn them
  from your wins and losses.
- You don't have to win every car. Decline by quoting very high; not answering
  costs a little goodwill.

## Drivers

- Freelancers living across Finland; not all work every day. You post a gig
  with a fee schedule; they book when it's worth their time.
- Cost to a driver: time on the road + trip to pickup + trip home by public
  transport. A driver living near the delivery is much cheaper.
- Evening, weekend, private-address and far-morning (night away) work costs
  more.
- Drivers learn how your fees rise; if they always rise, drivers wait.
- Notifications go to drivers near the pickup; most views are in the first
  minutes.
- Drivers can drop bookings (mostly when the fee only just paid). You can
  release a driver before they leave, for a fee.

## Being on time

- ≥ 90% of orders on time or you're not ranked.
- A driver books only if they can reach every stop in time (a 7 h drive due
  20:00 finds nobody after 13:00). Raise fees early; a late high fee usually
  finds nobody.
- Warning 3 h before the last possible pickup; after that only a higher fee or
  a direct offer helps.

## Combining cars

- One gig can hold several cars (≤ 12 h driving). A second car for a driver
  already on your work costs only the extra time and tickets.
- Direct offers: one driver, 10 minutes, your fee; ≤ 3 per driver per day; not
  read 23:00–07:00.

## Money

Margin = what dealers pay for delivered cars − driver fees − refunds − costs.
Late: ≤ 2 h 10% back, 2–24 h 25%, ≤ 2 business days 50%, later 100%. Not
delivered: no price + 2× penalty. Failed visit ≥ €25, premium car with
non-experienced driver €150, EV without needed charging €100.

## Levels

1–3 are about drivers (every quote wins), 4–6 add the market (competitor,
notes, unannounced events), 7–8 are a driver shortage where you must choose
which cars to win. Level 8 adds uneven towns, a dearer competitor with one
secret cheap day, and dealer trust. Final = level 8.

## Practice vs final

- **Practice:** your system moves the clock; one request per step; deterministic
  by seed; forkable; ≤ 8 open weeks; ranking runs use server-chosen seeds and
  can't be copied, revealed or undone.
- **Final:** Sunday 08:00 (set 07:30). Clock runs by itself (weekday hour =
  18 s, night hour = 3 s; ~34 min). 20 actions/s and 50 reads/s. If your
  system stops, the week goes on; restart, rebuild from state and events,
  continue. The server replays every team's week to check scores.

## Where to start (organisers' hints)

- **Choose your cars:** price to win the cheap-to-move ones.
- **Learn all week:** competitor prices move and react to you.
- **Know your drivers:** cost depends on where they are and live.
- **Post in time:** late raises find nobody; constant raises teach waiting.
- **Combine cars:** one two-car gig can beat two gigs.
- **Read the notes.**
- **Test on many weeks:** compare versions on the same 10–20 weeks.
