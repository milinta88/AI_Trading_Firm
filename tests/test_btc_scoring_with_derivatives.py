from __future__ import annotations

from datetime import UTC, datetime

from core.models import MarketDataPoint
from scoring.btc_scoring import BTCScoringEngine


def test_btc_scoring_uses_derivatives_when_available() -> None:
    engine = BTCScoringEngine()

    result = engine.score(
        {
            "btc_price": _snapshot("btc_price", "price", "OK", {"price": 108432.55, "symbol": "BTCUSDT"}),
            "btc_fear_greed": _snapshot(
                "btc_fear_greed",
                "fear_and_greed_index",
                "OK",
                {"value": 62, "classification": "Greed"},
            ),
            "btc_funding_rate": _snapshot(
                "btc_funding_rate",
                "funding_rate",
                "OK",
                {"funding_rate": 0.00038246, "symbol": "BTCUSDT"},
            ),
            "btc_open_interest": _snapshot(
                "btc_open_interest",
                "open_interest",
                "OK",
                {"open_interest": 10659.509, "symbol": "BTCUSDT"},
            ),
        }
    )

    assert result.total_score == 62
    assert result.bias == "Bullish"
    assert result.confidence == "Medium"
    assert result.data_completeness == 100
    assert any("modestly crowded long positioning" in reason for reason in result.reasons)
    assert any("used as context only until trend history is added" in reason for reason in result.reasons)
    assert any("confidence is capped at Medium" in warning for warning in result.warnings)


def test_btc_scoring_flags_overheated_derivatives_positioning() -> None:
    engine = BTCScoringEngine()

    result = engine.score(
        {
            "btc_price": _snapshot("btc_price", "price", "OK", {"price": 108432.55, "symbol": "BTCUSDT"}),
            "btc_fear_greed": _snapshot(
                "btc_fear_greed",
                "fear_and_greed_index",
                "OK",
                {"value": 80, "classification": "Extreme Greed"},
            ),
            "btc_funding_rate": _snapshot(
                "btc_funding_rate",
                "funding_rate",
                "OK",
                {"funding_rate": 0.0012, "symbol": "BTCUSDT"},
            ),
            "btc_open_interest": _snapshot(
                "btc_open_interest",
                "open_interest",
                "OK",
                {"open_interest": 11000.0, "symbol": "BTCUSDT"},
            ),
        }
    )

    assert result.total_score == 52
    assert result.bias == "Caution"
    assert result.confidence == "Medium"
    assert any("overheated" in warning.lower() for warning in result.warnings)
    assert any("confidence is capped at Medium" in warning for warning in result.warnings)


def _snapshot(
    key: str,
    data_type: str,
    status: str,
    value: dict[str, object],
) -> MarketDataPoint:
    return MarketDataPoint(
        key=key,
        asset="BTC",
        source="test",
        data_type=data_type,
        status=status,
        timestamp=datetime(2026, 5, 28, tzinfo=UTC),
        value=value,
    )
