from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agents.data_quality_bot import DataQualityBot
from core.models import MarketDataPoint


def test_data_quality_returns_warning_for_expected_placeholders() -> None:
    bot = DataQualityBot()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    market_data = {
        "btc_price": _snapshot("btc_price", "BTC", "price", "OK", now),
        "btc_fear_greed": _snapshot("btc_fear_greed", "BTC", "fear_and_greed_index", "OK", now),
        "gold_dxy": _snapshot("gold_dxy", "Gold", "dxy", "NOT_CONFIGURED", now),
    }

    result = bot.evaluate(market_data, now=now)

    assert result.overall_status == "WARNING"
    assert result.source_statuses["BTC Price"] == "OK"
    assert result.source_statuses["Gold Dxy"] == "NOT_CONFIGURED"


def test_data_quality_returns_fail_for_critical_source_failure() -> None:
    bot = DataQualityBot()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    market_data = {
        "btc_price": _snapshot("btc_price", "BTC", "price", "NOT_AVAILABLE", now, error_summary="HTTP 503"),
        "btc_fear_greed": _snapshot("btc_fear_greed", "BTC", "fear_and_greed_index", "OK", now),
    }

    result = bot.evaluate(market_data, now=now)

    assert result.overall_status == "FAIL"
    assert result.source_statuses["BTC Price"] == "FAIL"
    assert any("BTC Price is unavailable" in note for note in result.notes)


def test_data_quality_marks_old_fear_and_greed_as_stale() -> None:
    bot = DataQualityBot()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    market_data = {
        "btc_price": _snapshot("btc_price", "BTC", "price", "OK", now),
        "btc_fear_greed": _snapshot(
            "btc_fear_greed",
            "BTC",
            "fear_and_greed_index",
            "OK",
            now - timedelta(days=3),
        ),
    }

    result = bot.evaluate(market_data, now=now)

    assert result.overall_status == "FAIL"
    assert result.source_statuses["BTC Fear And Greed Index"] == "STALE"


def test_data_quality_respects_fred_monthly_stale_window_from_snapshot() -> None:
    bot = DataQualityBot()
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    market_data = {
        "gold_cpi": MarketDataPoint(
            key="gold_cpi",
            asset="Gold",
            source="FRED",
            data_type="cpi",
            status="OK",
            timestamp=datetime(2026, 4, 1, tzinfo=UTC),
            value={"latest_value": 320.0, "stale_after_days": 75},
            error_summary=None,
        ),
    }

    result = bot.evaluate(market_data, now=now)

    assert result.overall_status == "PASS"
    assert result.source_statuses["Gold Cpi"] == "OK"


def _snapshot(
    key: str,
    asset: str,
    data_type: str,
    status: str,
    timestamp: datetime,
    error_summary: str | None = None,
) -> MarketDataPoint:
    return MarketDataPoint(
        key=key,
        asset=asset,
        source="test",
        data_type=data_type,
        status=status,
        timestamp=timestamp,
        value={"value": 1} if status == "OK" else None,
        error_summary=error_summary,
    )
