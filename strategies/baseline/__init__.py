"""The baseline: the organisers' starter as strategies. See README.md in this folder."""

from strategies.baseline.admission import BaselineAdmission
from strategies.baseline.fees import BaselineFees
from strategies.baseline.notes import BaselineNotes
from strategies.baseline.pricing import BaselinePricing
from strategies.baseline.retry import FIRST_TRY, Retry

__all__ = ["FIRST_TRY", "BaselineAdmission", "BaselineFees", "BaselineNotes", "BaselinePricing", "Retry"]
