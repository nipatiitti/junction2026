"""Same-day admission, a system built on strategies/headroom: see README.md in this folder."""

from strategies.same_day.admission import Params as SameDayParams
from strategies.same_day.admission import SameDayAdmission

__all__ = ["SameDayAdmission", "SameDayParams"]
