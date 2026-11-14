# Simply Jack

The simplest dispatch system we have: a few plain rules in one file, [`dispatch.py`](dispatch.py), with every number
as a named constant at its top. It is built so that anyone on the team can read it top to bottom, and then improved
one small step at a time: play a week, change one thing, play again, and keep the change only if the margin went up.
Issue #280.

Jack makes two decisions. Everything else (posting gigs, reading notes, retries after a failed visit, bundling, direct
offers, the final) is the root [`dispatch.py`](../../dispatch.py), unchanged.

## The rules

**1. The price.** For each price request:

- Leave out every option that gives a driver less than `MIN_LEAD` to reach the car: the option's deadline, less the
  drive, less the minute the dealer decides.
- Quote each option that is left at its list price times `PRICE`, plus `TRUST_SHARE` of the dealer's trust. The trust
  is 1% for each order we delivered to that dealer on time, up to 25, and halves after a late one; the root pricing
  model counts it from the ledger.
- Decline when no option is left, or when the request's typical driver fee is more than `MAX_FEE_SHARE` of our price.
  A declined request gets a quote of ten times the list price, which loses at no cost.

**2. The driver fee.** For each gig: post it at `FEE_OPEN` times the typical fee, then raise it in `FEE_STEPS` even
steps to `FEE_TOP` times the typical fee, which it reaches `TOP_BEFORE` before the car's last pickup. With an hour or
less to go, the gig goes at the top fee at once.

## Run it

From the repository root, with the options of the root `dispatch.py` (`--level`, `--seed`, `--board`, `--final`):

```sh
uv run --env-file .env strategies/simply_jack/dispatch.py --level 8 --seed spread-9
```

Its weeks are saved like the root system's (`tools/record.py`), with the policy `simply-jack` and, in `meta.json`
under `settings`, the numbers the week was played with. At the end of a practice week it prints one line:

```text
Simply Jack: 949 requests quoted, 81 declined. Numbers: {'PRICE': 1.7, ...}
```

## The steps

Every step is one practice week at level 8 on the seed `spread-9`, played online after one change. A week is ranked
when at least 90% of its orders arrive on time. `spread-9` is the richest of our practice weeks: it is the only seed
on which any of our systems has passed €20,000 (the root `dispatch.py` made €13,716 there, `all_in` €16,048), so the
numbers here are higher than on `spread-1`. Jack is tuned to this one week; read the steps as a record of what each
change did, not as a forecast for other weeks.

LOG
