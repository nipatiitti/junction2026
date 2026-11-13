# Bundling

Puts the cars of several orders in one gig, as a chain that one driver drives: pickup, delivery, then the next car's
pickup. The chain saves the driver a trip home after one car and a trip out to the next, so it can pay less per car,
and in a shortage it needs fewer drivers. From level 3, where gigs with several cars start.

`dispatch.py` hands every new order to the `Bundler`, asks it each step which orders to post together and in what
stop order (`Desk.post_due`), and posts a group of one exactly as before.

## When orders wait

A request can carry a `batchId`: a dealer sends several cars from one yard at once. A bulk order is a batch of 30 to
40 cars, and smaller batches are common (on the level 8 week `smoke-1`, 390 of 1,033 requests came in batches of 3 or
more). An order of a batch waits in the pool until one of these comes first:

- 45 minutes after it was won (`hold`);
- the batch has no request open (its `respondBy` has passed) and sent none for 20 minutes (`quiet`);
- 6 hours before its `lastPickupAt` (`safe`): an order never waits later.

Any other order goes at the end of the step in which it was won, the same minute as before, but it can join a chain
with the orders waiting then. The loop wakes at the end of the earliest wait, so a held order is never forgotten. An
order whose deadline warning comes while it waits goes alone at once. A change of plan updates a waiting order, which
then goes with the new plan.

## How chains form

Each order that is ready heads a chain, earliest pickup window first, unless an earlier chain took it. The chain then
grows, one order at a time, by the order (ready or still waiting) that saves the most driver-minutes, while:

- the gig keeps the rules: at most 12 hours of planned driving by the road minutes, the drive between every two stops
  included (plates and charging stops do not count), and here no more than 8 hours (`max_drive`) and 3 cars
  (`max_cars`), as drivers cap their day;
- every stop is reached inside its window and when its site's stated hours show it open, with drives stretched by
  15% (`slow`), the first pickup at least 2 hours from now (`lead`), each delivery an hour before its window ends
  (`buffer`), and no wait of more than 2 hours for the next car (`max_wait`);
- the order has the same audience as the chain's first order (experienced driver, manual licence), so a bundle never
  shrinks the drivers who could take a car;
- the saving is at least 30 driver-minutes (`min_saving`).

The cost of a car alone is its drive, plus half a minute for each minute of the trip out (from where the nearest ten
drivers live, `strategies/fees` `Market.travel_minutes`) and of the trip home from its delivery place: time on public
transport costs a driver much less than time at the wheel. A chain costs the drives, one trip out, one trip home, and
half a minute for each road minute between a delivery and the next pickup. So a return leg (deliver at A, collect
at A) almost always joins. A second car from the same yard joins when going back to the yard costs less than the trips
that it saves, which is where few drivers live near the yard or its delivery towns.

## Stop order

The chain keeps each order's stops as `post` makes them for that order alone, one order after the other. A trade-in
stays one unit: the old car's pickup right after the new car's delivery. Each stop keeps its own window from the note
(`strategies/notes`), plates and charging. The audience is that of its orders: experienced when any car is premium,
a manual licence when any car needs one.

## The fee

The fee schedule of a bundle is planned by `strategies/fees` as one gig with the sum of its orders' typical fees,
scaled by the chain's cost over the sum of the cars' costs alone, kept between 0.6 and 0.95 (`fee_floor`,
`fee_cap`). So a bundle always pays less than its cars would alone. The price ceiling is the sum of the prices, and
the last pickup is the latest start that still collects every car of the chain by its order's `lastPickupAt`.

## When a bundle breaks up

A bundle goes back to one gig for each order, each at its own fees, when:

- the world refuses it (this should not happen: the checks above are stricter than the rules);
- it expires: each order is posted again without its stop windows, as a single gig would be;
- one of its orders gets its deadline warning and no driver holds the bundle;
- one of its orders changes its plan, or is cancelled and the bundle is withdrawn: the other orders go again alone.

A failed visit takes only that car out of the gig, and the driver goes on with the others, as the rules say.

At the end of a practice week, `dispatch.py` prints a line such as `Bundling orders 612, bundles 40, bundled orders 85,
bundled cars 88, bundle bookings 37, expired 2, split at warning 3`.

## Results

To be filled in from the bench.
