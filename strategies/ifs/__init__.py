"""The ifs system: plain if rules with every number in one file, and a search for better numbers. See README.md."""

from strategies.ifs.fees import IfFees
from strategies.ifs.rules import IfRules, Inputs, Params, load_values

__all__ = ["IfFees", "IfRules", "Inputs", "Params", "load_values"]
