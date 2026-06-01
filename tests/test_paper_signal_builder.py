from __future__ import annotations

from paper_trading.signal_builder import PaperSignalBuilder


def test_paper_signal_builder_creates_btc_long_candidate() -> None:
    signal = PaperSignalBuilder(default_risk_pct=0.25).build_signal(
        {
            "asset": "BTC",
            "total_score": 72,
            "bias": "Bullish",
            "confidence": "Medium",
            "data_completeness": 90,
        },
        latest_price=100.0,
    )

    assert signal.direction == "LONG"
    assert signal.intended_entry == 100.0
    assert signal.stop_loss == 98.0
    assert signal.take_profit == 104.0
    assert "PAPER TRADE" in signal.warnings[0]


def test_paper_signal_builder_returns_no_trade_when_rules_do_not_pass() -> None:
    signal = PaperSignalBuilder().build_signal(
        {
            "asset": "Gold",
            "total_score": 66,
            "bias": "Bullish",
            "confidence": "Low",
            "data_completeness": 80,
        },
        latest_price=2_000.0,
    )

    assert signal.direction == "NO_TRADE"
    assert signal.is_trade_candidate is False
    assert any("confidence" in reason for reason in signal.reasons)
