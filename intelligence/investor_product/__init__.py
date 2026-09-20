"""Unified Investor Intelligence Product composition."""

from intelligence.investor_product.schemas import InvestorIntelligenceView
from intelligence.investor_product.service import InvestorIntelligenceProductService

__all__ = ["InvestorIntelligenceProductService", "InvestorIntelligenceView"]
