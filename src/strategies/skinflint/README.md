# skinflint

A penny-pinching broker: dull prices, all effort on the driver fee.

- Price: the option `pickOption` picks (declines what cannot be served on time) at list x a fixed markup per
  option (`markupSameDay`, `markupNextDay`, `markupThreeDays`), plus `trustStep` per on-time order of the dealer.
- Fee: posted when won, opening at `open` x typical, plus premiums for hard work (private address, trade-in,
  premium car, Friday), minus `homeDiscount` when `homeDrivers` or more drivers live at the delivery town (plus
  `lonelyPremium` when none), minus `slackDiscount` per spare day. It rises on a curve (`curve`, convex) to
  `close` x typical at `closeLeadHours` before the last pickup. Urgent gigs and retries go steep
  (`urgentOpen` to `urgentClose`).
- Rescue: every `tickMinutes`, an open gig under `offerHours` to its last pickup gets up to 3 direct offers to
  drivers living at its delivery or pickup town, at the current fee x `offerFactor`.
