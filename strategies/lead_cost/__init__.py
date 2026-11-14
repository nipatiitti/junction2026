"""Lead-cost admission, a strategy for the systems of strategies/headroom and up: see README.md in this folder."""

from strategies.lead_cost.admission import LeadCostAdmission
from strategies.lead_cost.admission import Params as LeadCostParams

__all__ = ["LeadCostAdmission", "LeadCostParams"]
