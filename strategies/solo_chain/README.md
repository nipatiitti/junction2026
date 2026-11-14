# Cheap solo, then chain if unbooked (E2)

An experimental variant of [`all_in`](../all_in/README.md). The ordinary all_in pricing and fee schedules remain in
place. The timing-specific change is:

- a non-batch order with **at least six hours of pickup slack** gives its ordinary solo gig **45 minutes** to find a
  driver;
- while its timer runs, acceptable routes compose normally. A chain already available does not have to wait;
- when the timer expires and the gig is **still unbooked**, the desk makes **one** fallback attempt: withdraw the
  solo and return the order to the chain pool with whatever partners exist then;
- if a driver has already accepted the gig, never withdraw it. A booked or fully delivered order is never affected
  by the timer, and a fallback attempt never runs twice for an order.

The standard chain limits are unchanged: at most three cars, eight planned driving hours, audience match, individual
stop windows and the bundler's safe posting cutoff. The solo fee is the same low opening fee `all_in` normally uses;
there is no new blanket fee reduction.

From a separate working tree:

```sh
uv run strategies/solo_chain/dispatch.py --level 8 --seed tour-r1-d0cceb91
```

Saved weeks use policy `solo-chain`. This is experiment E2, not a replacement for `all_in`.
