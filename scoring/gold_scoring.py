from __future__ import annotations

from core.models import MarketDataPoint, TrendResult
from scoring.models import ScoreComponent, ScoreResult
from scoring.scoring_engine import RuleBasedScoringEngine


class GoldScoringEngine(RuleBasedScoringEngine):
    """Deterministic gold scoring using any available read-only macro inputs."""

    def score(
        self,
        market_data: dict[str, MarketDataPoint] | None = None,
        trend_context: dict[str, TrendResult] | None = None,
    ) -> ScoreResult:
        market_data = market_data or {}
        trend_context = trend_context or {}

        components = [
            self._score_directional_component(
                name="DXY",
                snapshot=market_data.get("gold_dxy"),
                bullish_points=8,
                bearish_points=-8,
                unavailable_reason="DXY live macro data is not configured yet.",
                bullish_reason="DXY is falling, which is generally supportive for gold.",
                bearish_reason="DXY is rising, which generally pressures gold.",
                trend=None,
            ),
            self._score_directional_component(
                name="US10Y",
                snapshot=market_data.get("gold_us10y"),
                bullish_points=10,
                bearish_points=-10,
                unavailable_reason="US10Y live macro data is not configured yet.",
                bullish_reason="US10Y is falling, which is generally supportive for gold.",
                bearish_reason="US10Y is rising, which generally pressures gold.",
                trend=trend_context.get("gold_us10y"),
            ),
            self._score_directional_component(
                name="Real Yield",
                snapshot=market_data.get("gold_real_yield"),
                bullish_points=15,
                bearish_points=-15,
                unavailable_reason="Real-yield live macro data is not configured yet.",
                bullish_reason="Real yield is falling, which is generally supportive for gold.",
                bearish_reason="Real yield is rising, which generally pressures gold.",
                trend=trend_context.get("gold_real_yield"),
            ),
            self._score_informational_component(
                name="Fed Funds",
                snapshot=market_data.get("gold_fed_funds"),
                unavailable_reason="Fed Funds live macro data is not configured yet.",
            ),
            self._score_informational_component(
                name="CPI",
                snapshot=market_data.get("gold_cpi"),
                unavailable_reason="CPI live macro data is not configured yet.",
            ),
            self._score_informational_component(
                name="Gold Spot Price",
                snapshot=market_data.get("gold_spot_price"),
                unavailable_reason="Gold spot price integration is not configured yet.",
            ),
        ]

        total_score = 50 + sum(component.score_contribution for component in components)
        total_score = self.clamp_score(total_score)
        data_completeness = self.calculate_data_completeness(components)
        warnings = [component.reason for component in components if component.status != "OK"]

        reasons = [
            self._build_summary_reason(market_data.get("gold_us10y"), "US10Y", trend_context.get("gold_us10y")),
            self._build_summary_reason(
                market_data.get("gold_real_yield"),
                "Real yield",
                trend_context.get("gold_real_yield"),
            ),
            self._build_summary_reason(market_data.get("gold_fed_funds"), "Fed Funds"),
        ]
        reasons = [reason for reason in reasons if reason]
        if market_data.get("gold_cpi") is None or market_data["gold_cpi"].status != "OK":
            reasons.append("CPI remains informational and may be unavailable without breaking the brief.")

        max_confidence = "Medium" if data_completeness >= 50 else "Low"
        confidence = self.derive_confidence(data_completeness, max_confidence=max_confidence)
        bias = self._derive_bias(total_score=total_score, data_completeness=data_completeness)

        return ScoreResult(
            asset="Gold",
            total_score=total_score,
            bias=bias,
            confidence=confidence,
            data_completeness=data_completeness,
            components=components,
            reasons=reasons,
            warnings=warnings,
        )

    @staticmethod
    def _score_directional_component(
        name: str,
        snapshot: MarketDataPoint | None,
        bullish_points: int,
        bearish_points: int,
        unavailable_reason: str,
        bullish_reason: str,
        bearish_reason: str,
        trend: TrendResult | None = None,
    ) -> ScoreComponent:
        if snapshot and snapshot.status == "OK" and snapshot.value and trend and trend.status == "OK":
            if trend.direction == "falling":
                score_contribution = bullish_points
                reason = f"{bullish_reason} Persisted trend: {trend.reason}"
            elif trend.direction == "rising":
                score_contribution = bearish_points
                reason = f"{bearish_reason} Persisted trend: {trend.reason}"
            else:
                score_contribution = 0
                reason = f"{name} persisted trend is flat, so it contributes neutrally."

            return ScoreComponent(
                name=name,
                status="OK",
                raw_value=snapshot.value,
                score_contribution=score_contribution,
                max_score=max(abs(bullish_points), abs(bearish_points)),
                reason=reason,
            )

        if snapshot and snapshot.status == "OK" and snapshot.value:
            direction = str(snapshot.value.get("direction", "unknown"))
            latest_value = snapshot.value.get("latest_value")
            if direction == "falling":
                score_contribution = bullish_points
                reason = f"{bullish_reason} Latest value: {latest_value}."
            elif direction == "rising":
                score_contribution = bearish_points
                reason = f"{bearish_reason} Latest value: {latest_value}."
            else:
                score_contribution = 0
                reason = f"{name} is flat or lacks trend context, so it contributes neutrally."

            return ScoreComponent(
                name=name,
                status="OK",
                raw_value=snapshot.value,
                score_contribution=score_contribution,
                max_score=max(abs(bullish_points), abs(bearish_points)),
                reason=reason,
            )

        status = snapshot.status if snapshot else "NOT_CONFIGURED"
        return ScoreComponent(
            name=name,
            status=status,
            raw_value=snapshot.value if snapshot else None,
            score_contribution=0,
            max_score=max(abs(bullish_points), abs(bearish_points)),
            reason=unavailable_reason if status == "NOT_CONFIGURED" else snapshot.error_summary or unavailable_reason,
        )

    @staticmethod
    def _score_informational_component(
        name: str,
        snapshot: MarketDataPoint | None,
        unavailable_reason: str,
    ) -> ScoreComponent:
        if snapshot and snapshot.status == "OK" and snapshot.value:
            latest_value = snapshot.value.get("latest_value")
            observation_date = snapshot.value.get("observation_date")
            return ScoreComponent(
                name=name,
                status="OK",
                raw_value=snapshot.value,
                score_contribution=0,
                max_score=5,
                reason=f"{name} latest observation: {latest_value} on {observation_date}.",
            )

        status = snapshot.status if snapshot else "NOT_CONFIGURED"
        return ScoreComponent(
            name=name,
            status=status,
            raw_value=snapshot.value if snapshot else None,
            score_contribution=0,
            max_score=5,
            reason=unavailable_reason if status == "NOT_CONFIGURED" else snapshot.error_summary or unavailable_reason,
        )

    @staticmethod
    def _derive_bias(total_score: int, data_completeness: int) -> str:
        if data_completeness < 40:
            return "Caution"
        if total_score >= 60:
            return "Bullish"
        if total_score <= 40:
            return "Bearish"
        return "Neutral"

    @staticmethod
    def _build_summary_reason(
        snapshot: MarketDataPoint | None,
        label: str,
        trend: TrendResult | None = None,
    ) -> str:
        if trend and trend.status == "OK":
            return trend.reason
        if snapshot and snapshot.status == "OK" and snapshot.value:
            latest_value = snapshot.value.get("latest_value")
            direction = snapshot.value.get("direction", "unknown")
            return f"{label} latest reading is {latest_value} with a {direction} trend."
        return f"{label} is not available from the current read-only macro feed."
