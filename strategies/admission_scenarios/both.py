"""Scenario 3 of 3: the other two at once (`strategies/admission_scenarios`).

Plays the root `dispatch.py` unchanged, except `Admission.Params.capacity_per_driver` **0.15** (from 0.10) *and* `cost_base`
**1.05** (from 1.15): a slightly fuller area alongside a slightly cheaper expected driver fee.

Run from the repository root, like any other system:
    uv run python strategies/admission_scenarios/both.py --level 8 --seed spread-1

Saved weeks are labelled policy `admission-both`. Only this scenario sets `SPREAD_ADMISSION_PARAMS`.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["SPREAD_ADMISSION_PARAMS"] = '{"capacity_per_driver": 0.15, "cost_base": 1.05}'

import dispatch
import tools.record

tools.record.POLICY = "admission-both"

if __name__ == "__main__":
    dispatch.main()
