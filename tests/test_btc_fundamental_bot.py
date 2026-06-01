from __future__ import annotations

from datetime import UTC, date, datetime

from agents.btc_fundamental_bot import BTCFundamentalBot
from core.models import MarketDataPoint


def test_btc_fundamental_bot_turns_bearish_on_extreme_fear() -> None:
    bot = BTCFundamentalBot()

    result = bot.analyze(
        date(2026, 5, 28),
        market_data={
            "btc_fear_greed": MarketDataPoint(
                key="btc_fear_greed",
                asset="BTC",
                source="Alternative.me",
                data_type="fear_and_greed_index",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"value": 15, "classification": "Extreme Fear"},
            )
        },
    )

    assert result.bias == "Bearish"
    assert result.score == 30
    assert result.confidence == "Low"


def test_btc_fundamental_bot_uses_live_read_only_inputs_when_available() -> None:
    bot = BTCFundamentalBot()

    result = bot.analyze(
        date(2026, 5, 28),
        market_data={
            "btc_price": MarketDataPoint(
                key="btc_price",
                asset="BTC",
                source="Binance Spot API",
                data_type="price",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"price": 108000.12, "symbol": "BTCUSDT"},
            ),
            "btc_fear_greed": MarketDataPoint(
                key="btc_fear_greed",
                asset="BTC",
                source="Alternative.me",
                data_type="fear_and_greed_index",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"value": 65, "classification": "Greed"},
            ),
        },
    )

    assert result.bias == "Bullish"
    assert result.score == 65
    assert any("108,000.12 USDT" in reason for reason in result.reasons)


def test_btc_fundamental_bot_falls_back_to_neutral_when_data_missing() -> None:
    bot = BTCFundamentalBot()

    result = bot.analyze(date(2026, 5, 28), market_data={})

    assert result.bias == "Caution"
    assert result.confidence == "Low"
    assert any("Fear & Greed data is unavailable" in reason for reason in result.reasons)
