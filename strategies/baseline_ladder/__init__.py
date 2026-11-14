"""The baseline with its quotes on a ladder and its fees on a ramp: see README.md in this folder."""

from strategies.baseline_ladder.fees import Params as RampParams
from strategies.baseline_ladder.fees import RampFees
from strategies.baseline_ladder.pricing import BaselineLadderPricing, Params

__all__ = ["BaselineLadderPricing", "Params", "RampFees", "RampParams"]
