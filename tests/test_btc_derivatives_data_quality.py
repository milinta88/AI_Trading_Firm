from __future__ import annotations

from datetime import UTC, datetime

from agents.data_quality_bot import DataQualityBot
from core.models import MarketDataPoint


def test_data_quality_passes_when_btc_derivatives_are_healthy() -> None:
    bot = DataQualityBot()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    market_data = {
        "btc_price": _snapshot("btc_price", "price", "OK", now, {"price": 108000.0}),
        "btc_fear_greed": _snapshot(
            "btc_fear_greed",
            "fear_and_greed_index",
            "OK",
            now,
            {"value": 62, "classification": "Greed"},
        ),
        "btc_funding_rate": _snapshot(
            "btc_funding_rate",
            "funding_rate",
            "OK",
            now,
            {"funding_rate": 0.00038246},
        ),
        "btc_open_interest": _snapshot(
            "btc_open_interest",
            "open_interest",
            "OK",
            now,
            {"open_interest": 10659.509},
        ),
    }

    result = bot.evaluate(market_data, now=now)

    assert result.overall_status == "PASS"
    assert result.source_statuses["BTC Funding Rate"] == "OK"
    assert result.source_statuses["BTC Open Interest"] == "OK"


def test_data_quality_warns_when_btc_derivatives_are_unavailable() -> None:
    bot = DataQualityBot()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    market_data = {
        "btc_price": _snapshot("btc_price", "price", "OK", now, {"price": 108000.0}),
        "btc_fear_greed": _snapshot(
            "btc_fear_greed",
            "fear_and_greed_index",
            "OK",
            now,
            {"value": 62, "classification": "Greed"},
        ),
        "btc_funding_rate": _snapshot(
            "btc_funding_rate",
            "funding_rate",
            "NOT_AVAILABLE",
            now,
            None,
            error_summary="HTTP 503",
        ),
        "btc_open_interest": _snapshot(
            "btc_open_interest",
            "open_interest",
            "NOT_AVAILABLE",
            now,
            None,
            error_summary="HTTP 503",
        ),
    }

    result = bot.evaluate(market_data, now=now)

    assert result.overall_status == "WARNING"
    assert result.source_statuses["BTC Funding Rate"] == "NOT_AVAILABLE"
    assert result.source_statuses["BTC Open Interest"] == "NOT_AVAILABLE"
    assert any("BTC Funding Rate is unavailable" in note for note in result.notes)


def _snapshot(
    key: str,
    data_type: str,
    status: str,
    timestamp: datetime,
    value: dict[str, object] | None,
    error_summary: str | None = None,
) -> MarketDataPoint:
    return MarketDataPoint(
        key=key,
        asset="BTC",
        source="test",
        data_type=data_type,
        status=status,
        timestamp=timestamp,
        value=value,
        error_summary=error_summary,
    )
