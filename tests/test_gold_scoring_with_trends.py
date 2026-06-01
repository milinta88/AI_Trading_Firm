from __future__ import annotations

from datetime import UTC, datetime

from core.models import MarketDataPoint, TrendResult
from scoring.gold_scoring import GoldScoringEngine


def test_gold_scoring_uses_persisted_yield_trends_when_available() -> None:
    timestamp = datetime(2026, 5, 29, tzinfo=UTC)
    market_data = {
        "gold_dxy": _snapshot("gold_dxy", "dxy", "NOT_CONFIGURED", None),
        "gold_us10y": _snapshot("gold_us10y", "us10y", "OK", {"latest_value": 4.2, "direction": "rising"}),
        "gold_real_yield": _snapshot(
            "gold_real_yield",
            "real_yield",
            "OK",
            {"latest_value": 1.9, "direction": "rising"},
        ),
        "gold_fed_funds": _snapshot("gold_fed_funds", "fed_funds", "OK", {"latest_value": 4.33}),
        "gold_cpi": _snapshot("gold_cpi", "cpi", "OK", {"latest_value": 320.0}),
        "gold_spot_price": _snapshot("gold_spot_price", "spot_price", "NOT_CONFIGURED", None),
    }
    trend_context = {
        "gold_us10y": TrendResult(
            "Gold",
            "us10y",
            "OK",
            4.2,
            4.4,
            -0.2,
            -4.55,
            "falling",
            2,
            "US10Y is falling versus the previous persisted snapshot, which is generally supportive for gold.",
        ),
        "gold_real_yield": TrendResult(
            "Gold",
            "real_yield",
            "OK",
            1.9,
            2.1,
            -0.2,
            -9.52,
            "falling",
            2,
            "Real yield is falling versus the previous persisted snapshot, which is generally supportive for gold.",
        ),
    }

    del timestamp
    result = GoldScoringEngine().score(market_data, trend_context=trend_context)

    assert result.total_score == 75
    assert result.bias == "Bullish"
    assert any("previous persisted snapshot" in reason for reason in result.reasons)


def _snapshot(
    key: str,
    data_type: str,
    status: str,
    value: dict[str, object] | None,
) -> MarketDataPoint:
    return MarketDataPoint(
        key=key,
        asset="Gold",
        source="test",
        data_type=data_type,
        status=status,
        timestamp=datetime(2026, 5, 29, tzinfo=UTC),
        value=value,
    )
