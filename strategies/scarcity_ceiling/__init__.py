"""Ceiling pricing on a scarcity-priced admission: see README.md in this folder."""

from strategies.scarcity_ceiling.admission import ChainScarcityAdmission
from strategies.scarcity_ceiling.admission import Params as ChainScarcityParams

__all__ = ["ChainScarcityAdmission", "ChainScarcityParams"]
