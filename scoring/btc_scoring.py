from __future__ import annotations

from core.models import MarketDataPoint, TrendResult
from scoring.models import ScoreComponent, ScoreResult
from scoring.scoring_engine import RuleBasedScoringEngine


class BTCScoringEngine(RuleBasedScoringEngine):
    """Deterministic BTC scoring using read-only Phase 1.x data."""

    def score(
        self,
        market_data: dict[str, MarketDataPoint] | None = None,
        trend_context: dict[str, TrendResult] | None = None,
    ) -> ScoreResult:
        market_data = market_data or {}
        trend_context = trend_context or {}

        price_component = self._score_price_component(market_data.get("btc_price"))
        fear_component, fear_warning = self._score_fear_and_greed_component(market_data.get("btc_fear_greed"))
        funding_component, funding_warning = self._score_funding_rate_component(market_data.get("btc_funding_rate"))
        open_interest_component, open_interest_warning, open_interest_trend_ready = self._score_open_interest_component(
            snapshot=market_data.get("btc_open_interest"),
            open_interest_trend=trend_context.get("btc_open_interest"),
        )

        components = [
            price_component,
            fear_component,
            funding_component,
            open_interest_component,
        ]
        total_score = self.clamp_score(50 + sum(component.score_contribution for component in components))
        data_completeness = self.calculate_data_completeness(components)

        reasons = [
            price_component.reason,
            fear_component.reason,
            funding_component.reason,
            open_interest_component.reason,
        ]

        warnings: list[str] = []
        if price_component.status != "OK":
            warnings.append("BTC public price data is missing or unavailable.")
        if fear_component.status != "OK":
            warnings.append("Fear & Greed data is missing or unavailable.")
        if funding_component.status != "OK":
            warnings.append("Funding rate data is unavailable, so confidence is capped.")
        if open_interest_component.status != "OK":
            warnings.append("Open interest data is unavailable, so confidence is capped.")
        elif not open_interest_trend_ready:
            warnings.append(
                "Open interest is available but used as context only until trend history is added; "
                "confidence is capped at Medium."
            )
        if open_interest_warning:
            warnings.append(open_interest_warning)
        if fear_warning:
            warnings.append(fear_warning)
        if funding_warning:
            warnings.append(funding_warning)

        confidence_cap = self._derive_confidence_cap(
            price_component=price_component,
            fear_component=fear_component,
            funding_component=funding_component,
            open_interest_component=open_interest_component,
            open_interest_trend_ready=open_interest_trend_ready,
            warnings=warnings,
        )
        confidence = self.derive_confidence(data_completeness, max_confidence=confidence_cap)
        bias = self._derive_bias(
            total_score=total_score,
            data_completeness=data_completeness,
            warnings=warnings,
            fear_status=fear_component.status,
        )

        return ScoreResult(
            asset="BTC",
            total_score=total_score,
            bias=bias,
            confidence=confidence,
            data_completeness=data_completeness,
            components=components,
            reasons=reasons,
            warnings=warnings,
        )

    def _score_price_component(self, snapshot: MarketDataPoint | None) -> ScoreComponent:
        if snapshot and snapshot.status == "OK" and snapshot.value:
            price = float(snapshot.value["price"])
            return ScoreComponent(
                name="BTC Price",
                status="OK",
                raw_value=snapshot.value,
                score_contribution=5,
                max_score=5,
                reason=f"Read-only BTCUSDT public price snapshot: {price:,.2f} USDT.",
            )

        status = snapshot.status if snapshot else "NOT_AVAILABLE"
        return ScoreComponent(
            name="BTC Price",
            status=status,
            raw_value=None,
            score_contribution=-5,
            max_score=5,
            reason="BTCUSDT public price snapshot is unavailable, so the score is penalized conservatively.",
        )

    def _score_fear_and_greed_component(
        self,
        snapshot: MarketDataPoint | None,
    ) -> tuple[ScoreComponent, str | None]:
        if snapshot and snapshot.status == "OK" and snapshot.value:
            value = int(snapshot.value["value"])
            classification = str(snapshot.value["classification"])

            if value <= 24:
                contribution = -15
                reason = f"Fear & Greed is {value} ({classification}), which signals risk-off sentiment."
                warning = None
            elif value <= 45:
                contribution = -5
                reason = f"Fear & Greed is {value} ({classification}), so sentiment remains cautious."
                warning = None
            elif value <= 55:
                contribution = 0
                reason = f"Fear & Greed is {value} ({classification}), which supports a neutral read."
                warning = None
            elif value <= 75:
                contribution = 10
                reason = f"Fear & Greed is {value} ({classification}), which is constructive for BTC."
                warning = None
            else:
                contribution = 5
                reason = f"Fear & Greed is {value} ({classification}), which is constructive but overheated."
                warning = "Fear & Greed is above 75, so sentiment may be overheated."

            return (
                ScoreComponent(
                    name="Fear & Greed",
                    status="OK",
                    raw_value=snapshot.value,
                    score_contribution=contribution,
                    max_score=15,
                    reason=reason,
                ),
                warning,
            )

        status = snapshot.status if snapshot else "NOT_AVAILABLE"
        return (
            ScoreComponent(
                name="Fear & Greed",
                status=status,
                raw_value=None,
                score_contribution=0,
                max_score=15,
                reason="Fear & Greed data is unavailable, so BTC falls back to a neutral sentiment component.",
            ),
            None,
        )

    def _score_funding_rate_component(
        self,
        snapshot: MarketDataPoint | None,
    ) -> tuple[ScoreComponent, str | None]:
        if snapshot and snapshot.status == "OK" and snapshot.value:
            funding_rate = float(snapshot.value["funding_rate"])
            funding_rate_pct = funding_rate * 100

            if funding_rate >= 0.0008:
                contribution = -8
                reason = (
                    f"Funding rate is {funding_rate_pct:.4f}%, which suggests aggressive long crowding in BTC perpetuals."
                )
                warning = "Funding rate is very positive, so BTC perpetual positioning may be overheated."
            elif funding_rate >= 0.0003:
                contribution = -3
                reason = (
                    f"Funding rate is {funding_rate_pct:.4f}%, which points to modestly crowded long positioning."
                )
                warning = None
            elif funding_rate <= -0.0008:
                contribution = 4
                reason = (
                    f"Funding rate is {funding_rate_pct:.4f}%, which can reflect stressed positioning and possible "
                    "contrarian support."
                )
                warning = "Funding rate is deeply negative, so bearish positioning stress remains elevated."
            elif funding_rate <= -0.0003:
                contribution = 2
                reason = f"Funding rate is {funding_rate_pct:.4f}%, which suggests mild washout and tentative support."
                warning = None
            else:
                contribution = 0
                reason = f"Funding rate is {funding_rate_pct:.4f}%, which is close to neutral."
                warning = None

            return (
                ScoreComponent(
                    name="Funding Rate",
                    status="OK",
                    raw_value=snapshot.value,
                    score_contribution=contribution,
                    max_score=10,
                    reason=reason,
                ),
                warning,
            )

        status = snapshot.status if snapshot else "NOT_AVAILABLE"
        reason = "Funding rate data is unavailable, so leverage sentiment is incomplete."
        if status == "NOT_CONFIGURED":
            reason = "Funding rate integration is not enabled yet."
        elif snapshot and snapshot.error_summary:
            reason = snapshot.error_summary

        return (
            ScoreComponent(
                name="Funding Rate",
                status=status,
                raw_value=snapshot.value if snapshot else None,
                score_contribution=0,
                max_score=10,
                reason=reason,
            ),
            None,
        )

    def _score_open_interest_component(
        self,
        snapshot: MarketDataPoint | None,
        open_interest_trend: TrendResult | None,
    ) -> tuple[ScoreComponent, str | None, bool]:
        if snapshot and snapshot.status == "OK" and snapshot.value:
            open_interest = float(snapshot.value["open_interest"])
            trend_ready = open_interest_trend is not None and open_interest_trend.status == "OK"
            if trend_ready:
                contribution, reason, warning = self._score_open_interest_trend(open_interest_trend)
            else:
                contribution = 0
                reason = (
                    f"Open interest is {open_interest:,.3f} and is available but used as context only until trend "
                    "history is added."
                )
                warning = None

            return (
                ScoreComponent(
                    name="Open Interest",
                    status="OK",
                    raw_value=snapshot.value,
                    score_contribution=contribution,
                    max_score=5,
                    reason=reason,
                ),
                warning,
                trend_ready,
            )

        status = snapshot.status if snapshot else "NOT_AVAILABLE"
        reason = "Open interest data is unavailable, so participation context is incomplete."
        if status == "NOT_CONFIGURED":
            reason = "Open-interest integration is not enabled yet."
        elif snapshot and snapshot.error_summary:
            reason = snapshot.error_summary

        return (
            ScoreComponent(
                name="Open Interest",
                status=status,
                raw_value=snapshot.value if snapshot else None,
                score_contribution=0,
                max_score=5,
                reason=reason,
            ),
            None,
            False,
        )

    @staticmethod
    def _score_open_interest_trend(open_interest_trend: TrendResult) -> tuple[int, str, str | None]:
        if open_interest_trend.direction == "rising" and "price is rising" in open_interest_trend.reason:
            return 3, open_interest_trend.reason, None
        if open_interest_trend.direction == "rising" and "price is falling" in open_interest_trend.reason:
            return -5, open_interest_trend.reason, "Open interest is rising while price is falling, so bearish pressure may be building."
        if open_interest_trend.direction == "falling":
            return 0, open_interest_trend.reason, None
        return 0, open_interest_trend.reason, None

    @staticmethod
    def _derive_confidence_cap(
        price_component: ScoreComponent,
        fear_component: ScoreComponent,
        funding_component: ScoreComponent,
        open_interest_component: ScoreComponent,
        open_interest_trend_ready: bool,
        warnings: list[str],
    ) -> str:
        if price_component.status != "OK" or fear_component.status != "OK":
            return "Medium"
        if (
            funding_component.status == "OK"
            and open_interest_component.status == "OK"
            and open_interest_trend_ready
            and not warnings
        ):
            return "High"
        if funding_component.status == "OK" and open_interest_component.status == "OK":
            return "Medium"
        return "Medium"

    @staticmethod
    def _derive_bias(
        total_score: int,
        data_completeness: int,
        warnings: list[str],
        fear_status: str,
    ) -> str:
        if total_score <= 40:
            return "Bearish"
        if data_completeness < 40:
            return "Caution"
        if any("overheated" in warning.lower() for warning in warnings):
            return "Caution"
        if total_score >= 60:
            return "Bullish"
        if fear_status != "OK":
            return "Caution"
        return "Neutral"
