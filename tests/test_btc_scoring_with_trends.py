from __future__ import annotations

from datetime import UTC, datetime

from core.models import MarketDataPoint, TrendResult
from scoring.btc_scoring import BTCScoringEngine


def test_btc_confidence_can_be_high_when_open_interest_trend_is_valid() -> None:
    result = BTCScoringEngine().score(_market_data(), trend_context=_trend_context("rising", "rising"))

    assert result.total_score == 65
    assert result.confidence == "High"
    assert result.data_completeness == 100
    assert not any("confidence is capped at Medium" in warning for warning in result.warnings)
    assert any("trend participation" in reason for reason in result.reasons)


def test_btc_open_interest_bearish_pressure_adds_warning_and_caps_confidence() -> None:
    result = BTCScoringEngine().score(_market_data(), trend_context=_trend_context("rising", "falling"))

    assert result.confidence == "Medium"
    assert any("bearish pressure" in warning for warning in result.warnings)


def _market_data() -> dict[str, MarketDataPoint]:
    timestamp = datetime(2026, 5, 29, tzinfo=UTC)
    return {
        "btc_price": MarketDataPoint(
            "btc_price",
            "BTC",
            "test",
            "price",
            "OK",
            timestamp,
            {"price": 108000.0, "symbol": "BTCUSDT"},
        ),
        "btc_fear_greed": MarketDataPoint(
            "btc_fear_greed",
            "BTC",
            "test",
            "fear_and_greed_index",
            "OK",
            timestamp,
            {"value": 62, "classification": "Greed"},
        ),
        "btc_funding_rate": MarketDataPoint(
            "btc_funding_rate",
            "BTC",
            "test",
            "funding_rate",
            "OK",
            timestamp,
            {"funding_rate": 0.00038246},
        ),
        "btc_open_interest": MarketDataPoint(
            "btc_open_interest",
            "BTC",
            "test",
            "open_interest",
            "OK",
            timestamp,
            {"open_interest": 10659.509},
        ),
    }


def _trend_context(open_interest_direction: str, price_direction: str) -> dict[str, TrendResult]:
    if open_interest_direction == "rising" and price_direction == "rising":
        reason = "BTC open interest is rising while price is rising, suggesting trend participation and leverage build-up."
    else:
        reason = "BTC open interest is rising while price is falling, suggesting possible bearish pressure."

    return {
        "btc_open_interest": TrendResult(
            asset="BTC",
            data_type="open_interest",
            status="OK",
            latest_value=1200.0,
            previous_value=1000.0,
            change_abs=200.0,
            change_pct=20.0,
            direction=open_interest_direction,
            lookback_points=2,
            reason=reason,
        ),
        "btc_price": TrendResult(
            asset="BTC",
            data_type="price",
            status="OK",
            latest_value=110.0 if price_direction == "rising" else 90.0,
            previous_value=100.0,
            change_abs=10.0 if price_direction == "rising" else -10.0,
            change_pct=10.0 if price_direction == "rising" else -10.0,
            direction=price_direction,
            lookback_points=2,
            reason=f"BTC price is {price_direction}.",
        ),
    }
