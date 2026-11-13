# Baseline

The organisers' starter, copied here, as the fixed baseline that our system is measured against. It is the code in
the kit's wheel (`vendor/spread-0.1.0-py3-none-any.whl`), file `spread/starter.py`, which uv installs as the package
`spread`. The copy is `baseline.py`; the strategy in it — the desk, the fees, the note reader and the play loop — is
the organisers' code, so a week played here is a baseline week.

README.md's [baseline to beat](../../README.md#the-baseline-to-beat) has its results: level 8 on the seed
`spread-1` ends at −€72,612.51, with 949 orders won and 45.5% of them on time.

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

The strategy is the organisers': the desk's answers, the fees (`rising` and `steep`), the note reader and the play
loop. Three mechanical changes make it pass our lint, and they change nothing:

- the unused `contextlib` import is gone;
- `Optional[X]` is written `X | None`;
- the default of `Desk.post` is a module-level `FIRST_TRY = Retry()`, as in `dispatch.py`; a `Retry` never changes.

The file is also formatted with ruff, like the rest of the repository.

The runner at the bottom is ours:

- it plays through `spread_proxy.ProxyClient`, so the run works in a cloud session, where the proxy holds the team
  key, as `dispatch.py` does;
- it saves the week with `record.Recorder`, so every online run of the baseline goes to `data/scrape/runs` and to the
  database, as every online run of `dispatch.py` does;
- it puts the repository root on the path first, so those two modules import when the file runs from another folder,
  as the bench runs it.

Do not improve the strategy here: a baseline that moves is no longer a baseline. Copy the file elsewhere when you want
to change it.
