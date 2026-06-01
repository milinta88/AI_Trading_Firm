from __future__ import annotations

from datetime import UTC, datetime

from agents.data_quality_bot import DataQualityBot
from core.models import MarketDataPoint


def test_data_quality_is_warning_when_btc_ok_and_some_gold_macro_not_configured() -> None:
    bot = DataQualityBot()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    market_data = {
        "btc_price": _snapshot("btc_price", "BTC", "price", "OK", now),
        "btc_fear_greed": _snapshot("btc_fear_greed", "BTC", "fear_and_greed_index", "OK", now),
        "gold_us10y": _snapshot("gold_us10y", "Gold", "us10y", "NOT_CONFIGURED", now, "No FRED key."),
        "gold_real_yield": _snapshot("gold_real_yield", "Gold", "real_yield", "OK", now),
        "gold_fed_funds": _snapshot("gold_fed_funds", "Gold", "fed_funds", "OK", now),
        "gold_cpi": _snapshot("gold_cpi", "Gold", "cpi", "OK", now),
    }

    result = bot.evaluate(market_data, now=now)

    assert result.overall_status == "WARNING"
    assert result.source_statuses["Gold Us10Y"] == "NOT_CONFIGURED"


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
        value={"latest_value": 1.0, "observation_date": "2026-05-28"} if status == "OK" else None,
        error_summary=error_summary,
    )

