# Baseline

The organisers' starter, rebuilt as strategies of the base class ([`../strategy.py`](../strategy.py)), as the fixed
baseline that our system is measured against. It is the code in the kit's wheel
(`vendor/spread-0.1.0-py3-none-any.whl`), file `spread/starter.py`, which uv installs as the package `spread`. The
decisions are the organisers' and do not change; this folder only re-homes them, so a baseline week is built, fed and
read the same way as every other strategy.

The unchanged starter on the seed `spread-1`, the baseline to beat:

| Level | Margin      | Orders won | On time | Ranked |
| ----- | ----------- | ---------- | ------- | ------ |
| 6     | -€1,172.51  | 555        | 95.9%   | yes    |
| 7     | -€50,442.49 | 817        | 52.3%   | no     |
| 8     | -€72,612.51 | 949        | 45.5%   | no     |

They match the handbook to the cent. The first `dispatch.py`, an unchanged copy of the starter, gave the same level 8
result. We measured levels 6 and 7 with the organisers' TypeScript starter, before we chose Python; the handbook says
that both starters play alike.

| File           | What it holds                                                                       |
| -------------- | ----------------------------------------------------------------------------------- |
| `baseline.py`  | The desk and the play loop: the starter's own, with the strategies below wired in   |
| `admission.py` | `BaselineAdmission`: every request is taken, and its first option is the one quoted |
| `pricing.py`   | `BaselinePricing`: the list price of each option                                    |
| `fees.py`      | `BaselineFees`: the starter's `rising` and `steep` fees, and the deadline warnings  |
| `notes.py`     | `BaselineNotes`: the note reader that narrows each stop's window                    |
| `retry.py`     | `Retry`: how a leg is posted again after a failed visit                             |

## Run it

From the repository root, with `SPREAD_URL` and `SPREAD_KEY` set (add `--env-file .env` after `uv run` to read them
from `.env`):

```sh
uv run --env-file .env python strategies/baseline/baseline.py --level 8 --seed spread-1
```

The same week with the kit's own starter is `uv run --env-file .env spread-starter --level 8 --seed spread-1`; the
copy plays alike, except that it goes through the repository's client and saves the week.

To compare the baseline with our system on the same seeds, use the seed bench:

```sh
uv run --env-file .env python -m strategies.bench strategies/baseline/baseline.py dispatch.py
```

## What is ours in the copy

The decisions are the organisers'. The quotes, the fees, the note reader and the failed-visit retry are strategies of
the base class, built and fed by the desk in `baseline.py` the same way `dispatch.py` builds and feeds its own; the
desk's answers and the play loop are unchanged. Every moved function is the starter's, byte for byte.

The runner at the bottom is ours:

- it plays through `spread_proxy.ProxyClient`, so the run works in a cloud session, where the proxy holds the team
  key, as `dispatch.py` does;
- it saves the week with `record.Recorder`, so every online run of the baseline goes to `data/scrape/runs` and to the
  database, as every online run of `dispatch.py` does.

Do not improve the decisions here: a baseline that moves is no longer a baseline. Copy the folder elsewhere when you
want to change them.
