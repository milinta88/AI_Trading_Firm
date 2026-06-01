from __future__ import annotations

import logging
from datetime import date

from core.models import AnalysisResult, MarketDataPoint, TrendResult
from scoring.gold_scoring import GoldScoringEngine

logger = logging.getLogger(__name__)


class GoldFundamentalBot:
    """Research-only gold fundamental bot backed by the current scoring engine."""

    name = "gold_fundamental_bot"

    def __init__(self) -> None:
        self.scoring_engine = GoldScoringEngine()

    def analyze(
        self,
        as_of: date,
        market_data: dict[str, MarketDataPoint] | None = None,
        trend_context: dict[str, TrendResult] | None = None,
    ) -> AnalysisResult:
        del as_of
        result = self.scoring_engine.score(market_data or {}, trend_context=trend_context or {})
        logger.info("Gold fundamental bot completed with %s bias and score %s.", result.bias, result.score)
        return result
