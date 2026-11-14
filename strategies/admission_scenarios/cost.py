"""Scenario 2 of 3: relax the admission **cost** buffer a little (`strategies/admission_scenarios`).

Plays the root `dispatch.py` unchanged, except that `Admission.Params.cost_base` goes from 1.15 to **1.05**: admission expects the
drivers to cost a little less, so some requests that used to fail the profit check (expected cost over price) are taken instead.

Run from the repository root, like any other system:
    uv run python strategies/admission_scenarios/cost.py --level 8 --seed spread-1

Saved weeks are labelled policy `admission-cost`. Only this scenario sets `SPREAD_ADMISSION_PARAMS`.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["SPREAD_ADMISSION_PARAMS"] = '{"cost_base": 1.05}'

import dispatch
import tools.record

tools.record.POLICY = "admission-cost"

if __name__ == "__main__":
    dispatch.main()
