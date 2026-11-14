"""Competitor herding, a system built on strategies/headroom: see README.md in this folder."""

from strategies.herd_competitor.pricing import HerdPricing
from strategies.herd_competitor.pricing import Params as HerdParams

__all__ = ["HerdParams", "HerdPricing"]
