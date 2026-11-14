"""Scenario 1 of 3: open the admission **capacity** gate a little (`strategies/admission_scenarios`).

Plays the root `dispatch.py` unchanged, except that `Admission.Params.capacity_per_driver` goes from 0.10 to **0.15**: an area
can hold a little more unbooked same-day orders before admission declines them for being full.

Run from the repository root, like any other system:
    uv run python strategies/admission_scenarios/capacity.py --level 8 --seed spread-1

Saved weeks are labelled policy `admission-capacity`. Only this scenario sets `SPREAD_ADMISSION_PARAMS`.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["SPREAD_ADMISSION_PARAMS"] = '{"capacity_per_driver": 0.15}'

import dispatch
import tools.record

tools.record.POLICY = "admission-capacity"

if __name__ == "__main__":
    dispatch.main()
