"""Ceiling's prices until the drivers fall behind, then max-margin's: a system built on strategies/max_margin, see
README.md in this folder."""

from strategies.tight_margin.pricing import Params, TightPricing

__all__ = ["Params", "TightPricing"]
