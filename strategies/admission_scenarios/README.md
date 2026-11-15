# Three admission scenarios

Issue #227. Thin entry points that play the unchanged root `dispatch.py` with one admission-safety knob altered, to test whether the
profit/capacity gates cost us profitable orders. The root dispatcher itself is untouched.

The offline admission replay of 50 saved weeks found the **profit** gate declines 20.6% of requests, the **capacity** gate 6.6%, and
the drivers actually cost 0.92× what admission expects on the median order. `late_slack` averages +25 orders of on-time slack. So the
changes here are modest and single-knob.

| Entry point   | Changed `Admission.Params` | Default | Here     | Weeks saved as policy |
| ------------- | -------------------------- | ------- | -------- | --------------------- |
| `capacity.py` | `capacity_per_driver`      | 0.10    | **0.15** | `admission-capacity`  |
| `cost.py`     | `cost_base`                | 1.15    | **1.05** | `admission-cost`      |
| `both.py`     | both of the above          | —       | —        | `admission-both`      |

Nothing else changes. `dispatch.py` reads the optional `SPREAD_ADMISSION_PARAMS` JSON env var in `Desk.__init__` and applies it with
`dataclasses.replace` on `Admission.Params`; without it the system is byte-identical to before. Everything is a fixed frozen `Params`
field, so the wrapper only has to set it before the desk builds.

## Run a week

From the repository root, with `SPREAD_URL`/`SPREAD_KEY` set:

```sh
uv run python strategies/admission_scenarios/capacity.py --level 8 --seed spread-1
uv run python strategies/admission_scenarios/cost.py     --level 8 --seed spread-1
uv run python strategies/admission_scenarios/both.py     --level 8 --seed spread-1
```

The bench runs the files like any other version and compares them with the unchanged root on the same seeds. Practice weeks only.

```sh
uv run python -m strategies.bench \
  dispatch.py \
  strategies/admission_scenarios/capacity.py \
  strategies/admission_scenarios/cost.py \
  strategies/admission_scenarios/both.py \
  --level 8 --seeds spread-1..spread-50 --jobs 8
```

Adopt a knob only if the net margin on the same seeds beats the paired noise band while ranked weeks stay ≥ 99% and undelivered orders
do not rise; order count alone is not the metric, since `price_ladder` already shows more orders can earn less.
