from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.config import StrategyHypothesisConfig
from core.models import (
    DataQualityReport,
    MarketDataPoint,
    ResearchReadinessResult,
    StrategyHypothesis,
    TrendResult,
)
from scoring.models import ScoreResult


_CONFIDENCE_RANK = {
    "Low": 1,
    "Medium": 2,
    "High": 3,
}


class StrategyHypothesisEngine:
    """Builds deterministic research hypotheses from existing read-only workflow outputs."""

    def __init__(
        self,
        config: StrategyHypothesisConfig,
        database_path: Path | None = None,
    ) -> None:
        self.config = config
        self.database_path = database_path

    def generate_all(
        self,
        *,
        score_results: dict[str, ScoreResult],
        research_readiness: dict[str, ResearchReadinessResult],
        trend_context: dict[str, TrendResult],
        market_data: dict[str, MarketDataPoint],
        data_quality: DataQualityReport,
        created_at: datetime | None = None,
    ) -> dict[str, StrategyHypothesis]:
        timestamp = created_at or datetime.now(UTC)
        if not self.config.enabled:
            return {
                "BTC": self._disabled_hypothesis("BTC", timestamp),
                "Gold": self._disabled_hypothesis("Gold", timestamp),
            }

        return {
            "BTC": self._build_btc_hypothesis(
                score=score_results.get("BTC"),
                readiness=research_readiness.get("BTC"),
                trend_context=trend_context,
                market_data=market_data,
                data_quality=data_quality,
                created_at=timestamp,
            ),
            "Gold": self._build_gold_hypothesis(
                score=score_results.get("Gold"),
                readiness=research_readiness.get("Gold"),
                trend_context=trend_context,
                market_data=market_data,
                data_quality=data_quality,
                created_at=timestamp,
            ),
        }

    def load_latest(self) -> dict[str, StrategyHypothesis]:
        if not self.database_path or not self.database_path.exists():
            return {}

        try:
            with self._connect_read_only() as connection:
                if not self._table_exists(connection, "strategy_hypotheses"):
                    return {}
                rows = connection.execute("SELECT * FROM strategy_hypotheses ORDER BY id DESC").fetchall()
        except sqlite3.Error:
            return {}

        latest_by_asset: dict[str, StrategyHypothesis] = {}
        for row in rows:
            asset = str(row["asset"])
            if asset not in latest_by_asset:
                latest_by_asset[asset] = self._row_to_hypothesis(dict(row))
        return latest_by_asset

    def load_recent(self, limit: int = 25) -> list[StrategyHypothesis]:
        if not self.database_path or not self.database_path.exists():
            return []

        try:
            with self._connect_read_only() as connection:
                if not self._table_exists(connection, "strategy_hypotheses"):
                    return []
                rows = connection.execute(
                    "SELECT * FROM strategy_hypotheses ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        except sqlite3.Error:
            return []

        return [self._row_to_hypothesis(dict(row)) for row in rows]

    def _build_btc_hypothesis(
        self,
        *,
        score: ScoreResult | None,
        readiness: ResearchReadinessResult | None,
        trend_context: dict[str, TrendResult],
        market_data: dict[str, MarketDataPoint],
        data_quality: DataQualityReport,
        created_at: datetime,
    ) -> StrategyHypothesis:
        if score is None:
            return self._blocked_hypothesis(
                asset="BTC",
                family="BTC_NO_TRADE",
                created_at=created_at,
                blockers=["BTC score snapshot is not available for hypothesis generation."],
                warnings=[],
                reasons=["Hypothesis generation needs the latest BTC score snapshot."],
                invalidation_notes="Generate a fresh BTC score snapshot before reviewing this hypothesis.",
            )
        if readiness is None:
            return self._blocked_hypothesis(
                asset="BTC",
                family="BTC_NO_TRADE",
                created_at=created_at,
                blockers=["BTC research readiness is not available for hypothesis generation."],
                warnings=list(score.warnings),
                reasons=list(score.reasons),
                score=score,
                invalidation_notes="Generate a fresh BTC research-readiness snapshot before reviewing this hypothesis.",
            )

        warnings = _unique_items([*score.warnings, *readiness.warnings])
        if not readiness.decision_ready:
            return self._blocked_hypothesis(
                asset="BTC",
                family="BTC_NO_TRADE",
                created_at=created_at,
                blockers=list(readiness.no_trade_reasons),
                warnings=warnings,
                reasons=["BTC research readiness is not decision-ready."],
                readiness=readiness,
                score=score,
                invalidation_notes="Review BTC again after readiness blockers are cleared and fresh data is persisted.",
            )

        base = self._build_btc_candidate(
            score=score,
            readiness=readiness,
            trend_context=trend_context,
            market_data=market_data,
            created_at=created_at,
        )
        return self._finalize_hypothesis(
            base=base,
            asset="BTC",
            readiness=readiness,
            score=score,
            data_quality=data_quality,
            warnings=warnings,
        )

    def _build_gold_hypothesis(
        self,
        *,
        score: ScoreResult | None,
        readiness: ResearchReadinessResult | None,
        trend_context: dict[str, TrendResult],
        market_data: dict[str, MarketDataPoint],
        data_quality: DataQualityReport,
        created_at: datetime,
    ) -> StrategyHypothesis:
        if score is None:
            return self._blocked_hypothesis(
                asset="Gold",
                family="GOLD_NO_TRADE",
                created_at=created_at,
                blockers=["Gold score snapshot is not available for hypothesis generation."],
                warnings=[],
                reasons=["Hypothesis generation needs the latest Gold score snapshot."],
                invalidation_notes="Generate a fresh Gold score snapshot before reviewing this hypothesis.",
            )
        if readiness is None:
            return self._blocked_hypothesis(
                asset="Gold",
                family="GOLD_NO_TRADE",
                created_at=created_at,
                blockers=["Gold research readiness is not available for hypothesis generation."],
                warnings=list(score.warnings),
                reasons=list(score.reasons),
                score=score,
                invalidation_notes="Generate a fresh Gold research-readiness snapshot before reviewing this hypothesis.",
            )

        warnings = _unique_items([*score.warnings, *readiness.warnings])
        if not readiness.decision_ready or readiness.regime == "INSUFFICIENT_DATA":
            blockers = list(readiness.no_trade_reasons) or [
                "Gold regime remains INSUFFICIENT_DATA, so the hypothesis stays blocked."
            ]
            return self._blocked_hypothesis(
                asset="Gold",
                family="GOLD_NO_TRADE",
                created_at=created_at,
                blockers=blockers,
                warnings=warnings,
                reasons=["Gold research readiness is not decision-ready."],
                readiness=readiness,
                score=score,
                invalidation_notes="Review Gold again after more macro history is stored and readiness blockers are cleared.",
            )

        base = self._build_gold_candidate(
            score=score,
            readiness=readiness,
            trend_context=trend_context,
            market_data=market_data,
            created_at=created_at,
        )
        return self._finalize_hypothesis(
            base=base,
            asset="Gold",
            readiness=readiness,
            score=score,
            data_quality=data_quality,
            warnings=warnings,
        )

    def _build_btc_candidate(
        self,
        *,
        score: ScoreResult,
        readiness: ResearchReadinessResult,
        trend_context: dict[str, TrendResult],
        market_data: dict[str, MarketDataPoint],
        created_at: datetime,
    ) -> StrategyHypothesis:
        fear_value = _market_value(market_data.get("btc_fear_greed"), "value")
        price_trend = trend_context.get("btc_price")
        funding_trend = trend_context.get("btc_funding_rate")
        open_interest_trend = trend_context.get("btc_open_interest")

        if readiness.regime in {"TREND_UP", "TREND_DOWN"} and self._btc_trend_alignment(score, readiness.regime):
            direction = "LONG" if readiness.regime == "TREND_UP" else "SHORT"
            reasons = [
                f"BTC regime is {readiness.regime} with readiness {readiness.readiness_score}/100.",
                f"BTC score is {score.total_score}/100 with {score.confidence} confidence and {score.bias} bias.",
            ]
            if price_trend:
                reasons.append(price_trend.reason)
            if funding_trend:
                reasons.append(funding_trend.reason)
            if open_interest_trend:
                reasons.append(open_interest_trend.reason)
            return StrategyHypothesis(
                asset="BTC",
                hypothesis_name="BTC Trend Continuation Research Hypothesis",
                direction_bias=direction,
                regime=readiness.regime,
                readiness_score=readiness.readiness_score,
                score=score.total_score,
                confidence=score.confidence,
                data_completeness=score.data_completeness,
                hypothesis_status="ACTIVE",
                reasons=_unique_items(reasons),
                blockers=[],
                warnings=[],
                suggested_strategy_family="BTC_TREND_CONTINUATION",
                suggested_holding_period="1-5 days",
                invalidation_notes=(
                    "Invalidate if BTC leaves the current trend regime, the score bias flips, "
                    "or price/open-interest confirmation breaks down."
                ),
                created_at=created_at,
            )

        if fear_value is not None and fear_value <= 24 and score.total_score >= 50 and score.bias in {"Bullish", "Neutral"}:
            reasons = [
                f"Fear & Greed is deeply fearful at {int(fear_value)}, so a contrarian long watchlist idea is allowed.",
                f"BTC score is {score.total_score}/100 with {score.confidence} confidence, which keeps mean-reversion research viable.",
            ]
            if price_trend:
                reasons.append(price_trend.reason)
            return StrategyHypothesis(
                asset="BTC",
                hypothesis_name="BTC Sentiment Mean Reversion Research Hypothesis",
                direction_bias="LONG",
                regime=readiness.regime,
                readiness_score=readiness.readiness_score,
                score=score.total_score,
                confidence=score.confidence,
                data_completeness=score.data_completeness,
                hypothesis_status="WATCH",
                reasons=_unique_items(reasons),
                blockers=[],
                warnings=[],
                suggested_strategy_family="BTC_SENTIMENT_MEAN_REVERSION",
                suggested_holding_period="1-3 days",
                invalidation_notes="Invalidate if sentiment normalizes quickly or the BTC score loses constructive support.",
                created_at=created_at,
            )

        if fear_value is not None and fear_value >= 76 and score.total_score <= 55 and score.bias in {"Bearish", "Caution", "Neutral"}:
            reasons = [
                f"Fear & Greed is overheated at {int(fear_value)}, so a contrarian short watchlist idea is allowed.",
                f"BTC score is {score.total_score}/100 with {score.confidence} confidence, which keeps mean-reversion research viable.",
            ]
            if price_trend:
                reasons.append(price_trend.reason)
            return StrategyHypothesis(
                asset="BTC",
                hypothesis_name="BTC Sentiment Mean Reversion Research Hypothesis",
                direction_bias="SHORT",
                regime=readiness.regime,
                readiness_score=readiness.readiness_score,
                score=score.total_score,
                confidence=score.confidence,
                data_completeness=score.data_completeness,
                hypothesis_status="WATCH",
                reasons=_unique_items(reasons),
                blockers=[],
                warnings=[],
                suggested_strategy_family="BTC_SENTIMENT_MEAN_REVERSION",
                suggested_holding_period="1-3 days",
                invalidation_notes="Invalidate if sentiment cools quickly or the BTC score becomes more constructive.",
                created_at=created_at,
            )

        if self._all_market_status_ok(market_data, "btc_funding_rate", "btc_open_interest") and score.bias in {"Bullish", "Bearish"}:
            direction = "LONG" if score.bias == "Bullish" else "SHORT"
            reasons = [
                f"BTC score bias is {score.bias} with derivatives data fully available.",
                "Funding rate and open interest are healthy enough to keep a derivatives-confirmation hypothesis on watch.",
            ]
            if funding_trend:
                reasons.append(funding_trend.reason)
            if open_interest_trend:
                reasons.append(open_interest_trend.reason)
            return StrategyHypothesis(
                asset="BTC",
                hypothesis_name="BTC Derivatives Confirmation Research Hypothesis",
                direction_bias=direction,
                regime=readiness.regime,
                readiness_score=readiness.readiness_score,
                score=score.total_score,
                confidence=score.confidence,
                data_completeness=score.data_completeness,
                hypothesis_status="WATCH",
                reasons=_unique_items(reasons),
                blockers=[],
                warnings=[],
                suggested_strategy_family="BTC_DERIVATIVES_CONFIRMATION",
                suggested_holding_period="1-3 days",
                invalidation_notes="Invalidate if derivatives confirmation fades or the BTC score bias becomes neutral.",
                created_at=created_at,
            )

        return StrategyHypothesis(
            asset="BTC",
            hypothesis_name="BTC No-Trade Research Hypothesis",
            direction_bias="NEUTRAL",
            regime=readiness.regime,
            readiness_score=readiness.readiness_score,
            score=score.total_score,
            confidence=score.confidence,
            data_completeness=score.data_completeness,
            hypothesis_status="WATCH",
            reasons=[
                f"BTC regime is {readiness.regime}, but the current score/bias mix does not confirm a stronger strategy family yet."
            ],
            blockers=[
                "Current BTC inputs do not align with trend continuation, sentiment mean reversion, or derivatives confirmation criteria."
            ],
            warnings=[],
            suggested_strategy_family="BTC_NO_TRADE",
            suggested_holding_period="Watchlist only",
            invalidation_notes="Promote only after BTC regime, sentiment, and score alignment become clearer.",
            created_at=created_at,
        )

    def _build_gold_candidate(
        self,
        *,
        score: ScoreResult,
        readiness: ResearchReadinessResult,
        trend_context: dict[str, TrendResult],
        market_data: dict[str, MarketDataPoint],
        created_at: datetime,
    ) -> StrategyHypothesis:
        critical_keys = ("gold_us10y", "gold_real_yield", "gold_fed_funds", "gold_cpi", "gold_dxy", "gold_spot_price")
        missing_critical = [
            _snapshot_label(key)
            for key in critical_keys
            if not self._market_status_ok(market_data.get(key))
        ]
        if missing_critical:
            return StrategyHypothesis(
                asset="Gold",
                hypothesis_name="Gold No-Trade Research Hypothesis",
                direction_bias="NO_TRADE" if not self.config.allow_watch_when_not_ready else "NEUTRAL",
                regime=readiness.regime,
                readiness_score=readiness.readiness_score,
                score=score.total_score,
                confidence=score.confidence,
                data_completeness=score.data_completeness,
                hypothesis_status="WATCH" if self.config.allow_watch_when_not_ready else "BLOCKED",
                reasons=[
                    "Gold macro hypothesis review prefers DXY, spot price, and FRED macro inputs to all be healthy."
                ],
                blockers=[f"Healthy Gold macro inputs still missing or stale: {', '.join(missing_critical)}."],
                warnings=[],
                suggested_strategy_family="GOLD_NO_TRADE",
                suggested_holding_period="Watchlist only",
                invalidation_notes="Promote only after DXY, Gold spot, and core FRED macro inputs are all healthy.",
                created_at=created_at,
            )

        us10y_trend = trend_context.get("gold_us10y")
        real_yield_trend = trend_context.get("gold_real_yield")
        dxy_value = _market_value(market_data.get("gold_dxy"), "latest_value")
        spot_value = _market_value(market_data.get("gold_spot_price"), "latest_value")

        if real_yield_trend and real_yield_trend.status == "OK" and real_yield_trend.direction == "falling" and score.bias == "Bullish" and score.total_score >= 55:
            reasons = [
                f"Gold readiness is {readiness.readiness_score}/100 with regime {readiness.regime}.",
                "Real yield is falling, which is supportive for Gold research.",
                f"Gold score is {score.total_score}/100 with {score.confidence} confidence and Bullish bias.",
            ]
            reasons.append(real_yield_trend.reason)
            if us10y_trend:
                reasons.append(us10y_trend.reason)
            if dxy_value is not None:
                reasons.append(f"DXY is available at {dxy_value}, which keeps USD confirmation visible in the research stack.")
            if spot_value is not None:
                reasons.append(f"Gold spot is available at {spot_value}.")
            return StrategyHypothesis(
                asset="Gold",
                hypothesis_name="Gold Real Yield Reversal Research Hypothesis",
                direction_bias="LONG",
                regime=readiness.regime,
                readiness_score=readiness.readiness_score,
                score=score.total_score,
                confidence=score.confidence,
                data_completeness=score.data_completeness,
                hypothesis_status="ACTIVE",
                reasons=_unique_items(reasons),
                blockers=[],
                warnings=[],
                suggested_strategy_family="GOLD_REAL_YIELD_REVERSAL",
                suggested_holding_period="3-10 days",
                invalidation_notes="Invalidate if real yields stop falling or the Gold score loses constructive support.",
                created_at=created_at,
            )

        if readiness.regime == "MACRO_BEARISH" and score.bias in {"Bearish", "Caution"}:
            reasons = [
                f"Gold readiness is {readiness.readiness_score}/100 with macro regime {readiness.regime}.",
                f"Gold score is {score.total_score}/100 with {score.confidence} confidence and {score.bias} bias.",
            ]
            if us10y_trend:
                reasons.append(us10y_trend.reason)
            if real_yield_trend:
                reasons.append(real_yield_trend.reason)
            if dxy_value is not None:
                reasons.append(f"DXY is available at {dxy_value}, which supports macro-pressure review.")
            return StrategyHypothesis(
                asset="Gold",
                hypothesis_name="Gold Macro Pressure Research Hypothesis",
                direction_bias="SHORT",
                regime=readiness.regime,
                readiness_score=readiness.readiness_score,
                score=score.total_score,
                confidence=score.confidence,
                data_completeness=score.data_completeness,
                hypothesis_status="ACTIVE",
                reasons=_unique_items(reasons),
                blockers=[],
                warnings=[],
                suggested_strategy_family="GOLD_MACRO_PRESSURE",
                suggested_holding_period="3-10 days",
                invalidation_notes="Invalidate if yields stop pressuring Gold or the score bias turns constructive.",
                created_at=created_at,
            )

        if score.bias in {"Bullish", "Bearish"} and dxy_value is not None and spot_value is not None:
            direction = "LONG" if score.bias == "Bullish" else "SHORT"
            reasons = [
                f"DXY ({dxy_value}) and Gold spot ({spot_value}) are both available for read-only confirmation.",
                f"Gold score bias is {score.bias} with readiness {readiness.readiness_score}/100.",
            ]
            if real_yield_trend:
                reasons.append(real_yield_trend.reason)
            return StrategyHypothesis(
                asset="Gold",
                hypothesis_name="Gold USD DXY Confirmation Research Hypothesis",
                direction_bias=direction,
                regime=readiness.regime,
                readiness_score=readiness.readiness_score,
                score=score.total_score,
                confidence=score.confidence,
                data_completeness=score.data_completeness,
                hypothesis_status="WATCH",
                reasons=_unique_items(reasons),
                blockers=[],
                warnings=[],
                suggested_strategy_family="GOLD_USD_DXY_CONFIRMATION",
                suggested_holding_period="2-7 days",
                invalidation_notes="Invalidate if USD/Gold snapshot confirmation weakens or the Gold score bias turns neutral.",
                created_at=created_at,
            )

        return StrategyHypothesis(
            asset="Gold",
            hypothesis_name="Gold No-Trade Research Hypothesis",
            direction_bias="NEUTRAL",
            regime=readiness.regime,
            readiness_score=readiness.readiness_score,
            score=score.total_score,
            confidence=score.confidence,
            data_completeness=score.data_completeness,
            hypothesis_status="WATCH",
            reasons=[
                f"Gold regime is {readiness.regime}, but the current macro stack does not yet align with a stronger strategy family."
            ],
            blockers=[
                "Current Gold inputs do not align with macro pressure, real-yield reversal, or USD/DXY confirmation criteria."
            ],
            warnings=[],
            suggested_strategy_family="GOLD_NO_TRADE",
            suggested_holding_period="Watchlist only",
            invalidation_notes="Promote only after Gold macro regime and score alignment become clearer.",
            created_at=created_at,
        )

    def _finalize_hypothesis(
        self,
        *,
        base: StrategyHypothesis,
        asset: str,
        readiness: ResearchReadinessResult,
        score: ScoreResult,
        data_quality: DataQualityReport,
        warnings: list[str],
    ) -> StrategyHypothesis:
        blockers = list(base.blockers)
        merged_warnings = _unique_items([*base.warnings, *warnings])
        status = base.hypothesis_status
        direction = base.direction_bias

        if readiness.readiness_score < self.config.min_readiness_score:
            blockers.append(
                f"Readiness score {readiness.readiness_score} is below the strategy minimum {self.config.min_readiness_score}."
            )
            if self.config.allow_watch_when_not_ready and status != "BLOCKED":
                status = "WATCH"
            else:
                status = "BLOCKED"
                direction = "NO_TRADE"

        if self._confidence_rank(score.confidence) < self._confidence_rank(self.config.min_confidence):
            blockers.append(
                f"{asset} confidence {score.confidence} is below the strategy minimum {self.config.min_confidence}."
            )
            if self.config.allow_watch_when_not_ready and status != "BLOCKED":
                status = "WATCH"
            else:
                status = "BLOCKED"
                direction = "NO_TRADE"

        if data_quality.overall_status == "FAIL":
            blockers.append("Data quality overall status is FAIL, so the hypothesis is blocked.")
            status = "BLOCKED"
            direction = "NO_TRADE"
        elif data_quality.overall_status != "PASS":
            merged_warnings.append(
                f"Data quality overall status is {data_quality.overall_status}, so the hypothesis remains on watch."
            )
            if status == "ACTIVE":
                status = "WATCH"

        return StrategyHypothesis(
            asset=base.asset,
            hypothesis_name=base.hypothesis_name,
            direction_bias=direction,
            regime=base.regime,
            readiness_score=base.readiness_score,
            score=base.score,
            confidence=base.confidence,
            data_completeness=base.data_completeness,
            hypothesis_status=status,
            reasons=base.reasons,
            blockers=_unique_items(blockers),
            warnings=merged_warnings,
            suggested_strategy_family=base.suggested_strategy_family,
            suggested_holding_period=base.suggested_holding_period,
            invalidation_notes=base.invalidation_notes,
            created_at=base.created_at,
        )

    def _disabled_hypothesis(self, asset: str, created_at: datetime) -> StrategyHypothesis:
        family = "BTC_NO_TRADE" if asset == "BTC" else "GOLD_NO_TRADE"
        return self._blocked_hypothesis(
            asset=asset,
            family=family,
            created_at=created_at,
            blockers=["Strategy hypothesis generation is disabled in config."],
            warnings=[],
            reasons=["Research hypothesis generation is disabled."],
            invalidation_notes="Enable strategy_hypotheses in config before reviewing research hypotheses.",
        )

    def _blocked_hypothesis(
        self,
        *,
        asset: str,
        family: str,
        created_at: datetime,
        blockers: list[str],
        warnings: list[str],
        reasons: list[str],
        invalidation_notes: str,
        readiness: ResearchReadinessResult | None = None,
        score: ScoreResult | None = None,
    ) -> StrategyHypothesis:
        return StrategyHypothesis(
            asset=asset,
            hypothesis_name=_hypothesis_name_for_family(family),
            direction_bias="NO_TRADE",
            regime=readiness.regime if readiness else "INSUFFICIENT_DATA",
            readiness_score=readiness.readiness_score if readiness else 0,
            score=score.total_score if score else 0,
            confidence=score.confidence if score else "Low",
            data_completeness=score.data_completeness if score else 0,
            hypothesis_status="BLOCKED",
            reasons=_unique_items(reasons),
            blockers=_unique_items(blockers),
            warnings=_unique_items(warnings),
            suggested_strategy_family=family,
            suggested_holding_period="Watchlist only",
            invalidation_notes=invalidation_notes,
            created_at=created_at,
        )

    @staticmethod
    def _market_status_ok(snapshot: MarketDataPoint | None) -> bool:
        return snapshot is not None and snapshot.status == "OK"

    def _all_market_status_ok(self, market_data: dict[str, MarketDataPoint], *keys: str) -> bool:
        return all(self._market_status_ok(market_data.get(key)) for key in keys)

    @staticmethod
    def _btc_trend_alignment(score: ScoreResult, regime: str) -> bool:
        if regime == "TREND_UP":
            return score.bias == "Bullish" and score.total_score >= 55
        if regime == "TREND_DOWN":
            return score.bias == "Bearish" and score.total_score <= 45
        return False

    @staticmethod
    def _confidence_rank(value: str) -> int:
        return _CONFIDENCE_RANK.get(value, 0)

    def _connect_read_only(self) -> sqlite3.Connection:
        assert self.database_path is not None
        uri = f"{self.database_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _row_to_hypothesis(row: dict[str, Any]) -> StrategyHypothesis:
        return StrategyHypothesis(
            asset=str(row.get("asset") or "UNKNOWN"),
            hypothesis_name=str(row.get("hypothesis_name") or ""),
            direction_bias=str(row.get("direction_bias") or "NO_TRADE"),
            regime=str(row.get("regime") or "INSUFFICIENT_DATA"),
            readiness_score=int(row.get("readiness_score") or 0),
            score=int(row.get("score") or 0),
            confidence=str(row.get("confidence") or "Low"),
            data_completeness=int(row.get("data_completeness") or 0),
            hypothesis_status=str(row.get("hypothesis_status") or "BLOCKED"),
            reasons=_json_list(row.get("reasons_json")),
            blockers=_json_list(row.get("blockers_json")),
            warnings=_json_list(row.get("warnings_json")),
            suggested_strategy_family=str(row.get("suggested_strategy_family") or ""),
            suggested_holding_period=str(row.get("suggested_holding_period") or "Watchlist only"),
            invalidation_notes=str(row.get("invalidation_notes") or ""),
            created_at=_parse_datetime(row.get("created_at")),
        )


def _market_value(snapshot: MarketDataPoint | None, key: str) -> float | None:
    if snapshot is None or snapshot.status != "OK" or not isinstance(snapshot.value, dict):
        return None
    raw_value = snapshot.value.get(key)
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _snapshot_label(key: str) -> str:
    return key.replace("gold_", "Gold ").replace("btc_", "BTC ").replace("_", " ").title()


def _unique_items(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in unique:
            continue
        unique.append(normalized)
    return unique


def _hypothesis_name_for_family(family: str) -> str:
    names = {
        "BTC_TREND_CONTINUATION": "BTC Trend Continuation Research Hypothesis",
        "BTC_SENTIMENT_MEAN_REVERSION": "BTC Sentiment Mean Reversion Research Hypothesis",
        "BTC_DERIVATIVES_CONFIRMATION": "BTC Derivatives Confirmation Research Hypothesis",
        "BTC_NO_TRADE": "BTC No-Trade Research Hypothesis",
        "GOLD_MACRO_PRESSURE": "Gold Macro Pressure Research Hypothesis",
        "GOLD_REAL_YIELD_REVERSAL": "Gold Real Yield Reversal Research Hypothesis",
        "GOLD_USD_DXY_CONFIRMATION": "Gold USD DXY Confirmation Research Hypothesis",
        "GOLD_NO_TRADE": "Gold No-Trade Research Hypothesis",
    }
    return names.get(family, f"{family.replace('_', ' ').title()} Research Hypothesis")


def _json_list(raw_value: Any) -> list[str]:
    if raw_value in {None, ""}:
        return []
    try:
        parsed = json.loads(str(raw_value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _parse_datetime(raw_value: Any) -> datetime:
    if raw_value in {None, ""}:
        return datetime.now(UTC)
    text = str(raw_value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
