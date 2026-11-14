"""Flu-guard admission, a system built on strategies/soft_top: see README.md in this folder."""

from strategies.flu_guard.admission import FluGuardAdmission
from strategies.flu_guard.admission import Params as FluGuardParams

__all__ = ["FluGuardAdmission", "FluGuardParams"]
