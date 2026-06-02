from __future__ import annotations

from datetime import UTC, datetime

from analytics.strategy_hypothesis import StrategyHypothesisEngine
from core.config import StrategyHypothesisConfig
from core.models import DataQualityReport, MarketDataPoint, ResearchReadinessResult, TrendResult
from scoring.models import ScoreResult


def test_strategy_hypothesis_blocks_when_readiness_is_false() -> None:
    engine = StrategyHypothesisEngine(_config())

    hypotheses = engine.generate_all(
        score_results={
            "BTC": _score("BTC", total_score=62, bias="Bullish", confidence="Medium"),
        },
        research_readiness={
            "BTC": ResearchReadinessResult(
                asset="BTC",
                readiness_score=45,
                regime="INSUFFICIENT_DATA",
                data_completeness=60,
                stale_sources=[],
                missing_sources=["BTC Open Interest"],
                warnings=[],
                decision_ready=False,
                no_trade_reasons=["BTC readiness is below threshold."],
            ),
        },
        trend_context={},
        market_data={},
        data_quality=DataQualityReport(overall_status="PASS", source_statuses={}, notes=[]),
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    btc = hypotheses["BTC"]
    assert btc.hypothesis_status == "BLOCKED"
    assert btc.direction_bias == "NO_TRADE"
    assert "BTC readiness is below threshold." in btc.blockers


def test_strategy_hypothesis_creates_btc_trend_continuation_when_ready() -> None:
    engine = StrategyHypothesisEngine(_config())

    hypotheses = engine.generate_all(
        score_results={
            "BTC": _score("BTC", total_score=68, bias="Bullish", confidence="High"),
        },
        research_readiness={
            "BTC": ResearchReadinessResult(
                asset="BTC",
                readiness_score=88,
                regime="TREND_UP",
                data_completeness=100,
                stale_sources=[],
                missing_sources=[],
                warnings=[],
                decision_ready=True,
                no_trade_reasons=[],
            ),
        },
        trend_context={
            "btc_price": _trend("BTC", "price", "rising", "BTC price is rising across persisted snapshots."),
            "btc_funding_rate": _trend(
                "BTC",
                "funding_rate",
                "rising",
                "BTC funding rate is rising but still orderly.",
            ),
            "btc_open_interest": _trend(
                "BTC",
                "open_interest",
                "rising",
                "BTC open interest is rising while price is rising, suggesting trend participation.",
            ),
        },
        market_data={
            "btc_fear_greed": _snapshot("btc_fear_greed", "BTC", "fear_and_greed_index", {"value": 60, "classification": "Greed"}),
            "btc_funding_rate": _snapshot("btc_funding_rate", "BTC", "funding_rate", {"funding_rate": 0.0001}),
            "btc_open_interest": _snapshot("btc_open_interest", "BTC", "open_interest", {"open_interest": 1000.0}),
        },
        data_quality=DataQualityReport(overall_status="PASS", source_statuses={}, notes=[]),
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    btc = hypotheses["BTC"]
    assert btc.hypothesis_status == "ACTIVE"
    assert btc.direction_bias == "LONG"
    assert btc.suggested_strategy_family == "BTC_TREND_CONTINUATION"


def test_strategy_hypothesis_blocks_gold_when_regime_is_insufficient() -> None:
    engine = StrategyHypothesisEngine(_config())

    hypotheses = engine.generate_all(
        score_results={
            "Gold": _score("Gold", total_score=52, bias="Neutral", confidence="Medium"),
        },
        research_readiness={
            "Gold": ResearchReadinessResult(
                asset="Gold",
                readiness_score=40,
                regime="INSUFFICIENT_DATA",
                data_completeness=60,
                stale_sources=[],
                missing_sources=["Gold DXY"],
                warnings=[],
                decision_ready=False,
                no_trade_reasons=["Gold regime is still INSUFFICIENT_DATA."],
            ),
        },
        trend_context={},
        market_data={},
        data_quality=DataQualityReport(overall_status="PASS", source_statuses={}, notes=[]),
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    gold = hypotheses["Gold"]
    assert gold.hypothesis_status == "BLOCKED"
    assert gold.direction_bias == "NO_TRADE"
    assert gold.suggested_strategy_family == "GOLD_NO_TRADE"
    assert "Gold regime is still INSUFFICIENT_DATA." in gold.blockers


def _config() -> StrategyHypothesisConfig:
    return StrategyHypothesisConfig(
        enabled=True,
        min_readiness_score=70,
        min_confidence="Medium",
        allow_watch_when_not_ready=True,
    )


def _score(asset: str, total_score: int, bias: str, confidence: str) -> ScoreResult:
    return ScoreResult(
        asset=asset,
        total_score=total_score,
        bias=bias,
        confidence=confidence,
        data_completeness=100,
        reasons=[f"{asset} score is available."],
        warnings=[],
    )


def _trend(asset: str, data_type: str, direction: str, reason: str) -> TrendResult:
    return TrendResult(
        asset=asset,
        data_type=data_type,
        status="OK",
        latest_value=1.0,
        previous_value=0.9,
        change_abs=0.1,
        change_pct=10.0,
        direction=direction,
        lookback_points=5,
        reason=reason,
    )


def _snapshot(key: str, asset: str, data_type: str, value: dict[str, object]) -> MarketDataPoint:
    return MarketDataPoint(
        key=key,
        asset=asset,
        source="test",
        data_type=data_type,
        status="OK",
        timestamp=datetime(2026, 6, 2, tzinfo=UTC),
        value=value,
    )
