from __future__ import annotations

import logging
from datetime import date

from core.models import AnalysisResult, MarketDataPoint, TrendResult
from scoring.btc_scoring import BTCScoringEngine

logger = logging.getLogger(__name__)


class BTCFundamentalBot:
    """Research-only BTC fundamental bot backed by the current scoring engine."""

    name = "btc_fundamental_bot"

    def __init__(self) -> None:
        self.scoring_engine = BTCScoringEngine()

    def analyze(
        self,
        as_of: date,
        market_data: dict[str, MarketDataPoint] | None = None,
        trend_context: dict[str, TrendResult] | None = None,
    ) -> AnalysisResult:
        del as_of
        result = self.scoring_engine.score(market_data or {}, trend_context=trend_context or {})
        logger.info("BTC fundamental bot completed with %s bias and score %s.", result.bias, result.score)
        return result
