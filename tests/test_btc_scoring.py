from __future__ import annotations

from datetime import UTC, datetime

from core.models import MarketDataPoint
from scoring.btc_scoring import BTCScoringEngine


def test_btc_scoring_is_bearish_in_extreme_fear() -> None:
    engine = BTCScoringEngine()

    result = engine.score(
        {
            "btc_price": MarketDataPoint(
                key="btc_price",
                asset="BTC",
                source="Binance Spot API",
                data_type="price",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"price": 100000.0, "symbol": "BTCUSDT"},
            ),
            "btc_fear_greed": MarketDataPoint(
                key="btc_fear_greed",
                asset="BTC",
                source="Alternative.me",
                data_type="fear_and_greed_index",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"value": 20, "classification": "Extreme Fear"},
            ),
            "btc_funding_rate": MarketDataPoint(
                key="btc_funding_rate",
                asset="BTC",
                source="Binance Public Futures",
                data_type="funding_rate",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
            ),
            "btc_open_interest": MarketDataPoint(
                key="btc_open_interest",
                asset="BTC",
                source="Binance Public Futures",
                data_type="open_interest",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
            ),
        }
    )

    assert result.total_score == 40
    assert result.bias == "Bearish"
    assert result.confidence == "Medium"
    assert result.data_completeness == 50


def test_btc_scoring_adds_overheated_warning() -> None:
    engine = BTCScoringEngine()

    result = engine.score(
        {
            "btc_price": MarketDataPoint(
                key="btc_price",
                asset="BTC",
                source="Binance Spot API",
                data_type="price",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"price": 110000.0, "symbol": "BTCUSDT"},
            ),
            "btc_fear_greed": MarketDataPoint(
                key="btc_fear_greed",
                asset="BTC",
                source="Alternative.me",
                data_type="fear_and_greed_index",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"value": 80, "classification": "Extreme Greed"},
            ),
            "btc_funding_rate": MarketDataPoint(
                key="btc_funding_rate",
                asset="BTC",
                source="Binance Public Futures",
                data_type="funding_rate",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
            ),
            "btc_open_interest": MarketDataPoint(
                key="btc_open_interest",
                asset="BTC",
                source="Binance Public Futures",
                data_type="open_interest",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
            ),
        }
    )

    assert result.total_score == 60
    assert result.bias == "Caution"
    assert any("overheated" in warning.lower() for warning in result.warnings)

