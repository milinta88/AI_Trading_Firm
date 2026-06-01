from __future__ import annotations

from core.config import PaperSignalConfig
from paper_trading.signal_builder import PaperSignalBuilder


def test_balanced_profile_can_accept_score_that_conservative_rejects() -> None:
    score = {
        "asset": "BTC",
        "total_score": 68,
        "bias": "Bullish",
        "confidence": "Medium",
        "data_completeness": 90,
    }

    conservative_signal = PaperSignalBuilder(signal_config=_signal_config(profile="conservative")).build_signal(
        score,
        latest_price=100.0,
    )
    balanced_signal = PaperSignalBuilder(signal_config=_signal_config(profile="balanced")).build_signal(
        score,
        latest_price=100.0,
    )

    assert conservative_signal.direction == "NO_TRADE"
    assert any(reason["code"] == "SCORE_BELOW_LONG_THRESHOLD" for reason in conservative_signal.review_reasons)
    assert balanced_signal.direction == "LONG"
    assert balanced_signal.active_profile == "balanced"


def test_exploratory_profile_allows_neutral_bias_and_marks_warning() -> None:
    signal = PaperSignalBuilder(signal_config=_signal_config(profile="exploratory")).build_signal(
        {
            "asset": "Gold",
            "total_score": 63,
            "bias": "Neutral",
            "confidence": "Low",
            "data_completeness": 70,
        },
        latest_price=2_000.0,
    )

    assert signal.direction == "LONG"
    assert signal.active_profile == "exploratory"
    assert any("Exploratory paper-signal tuning is enabled" in warning for warning in signal.warnings)


def test_signal_builder_records_confidence_reason_when_threshold_fails() -> None:
    signal = PaperSignalBuilder(signal_config=_signal_config(profile="conservative")).build_signal(
        {
            "asset": "BTC",
            "total_score": 75,
            "bias": "Bullish",
            "confidence": "Low",
            "data_completeness": 95,
        },
        latest_price=100.0,
    )

    assert signal.direction == "NO_TRADE"
    assert any(reason["code"] == "CONFIDENCE_TOO_LOW" for reason in signal.review_reasons)


def _signal_config(profile: str) -> PaperSignalConfig:
    if profile == "balanced":
        return PaperSignalConfig(
            profile="balanced",
            btc_long_score_threshold=67,
            btc_short_score_threshold=38,
            gold_long_score_threshold=67,
            gold_short_score_threshold=38,
            min_confidence="Medium",
            min_btc_data_completeness=75,
            min_gold_data_completeness=55,
            allow_neutral_bias=False,
            exploratory_mode=False,
        )
    if profile == "exploratory":
        return PaperSignalConfig(
            profile="exploratory",
            btc_long_score_threshold=62,
            btc_short_score_threshold=42,
            gold_long_score_threshold=62,
            gold_short_score_threshold=42,
            min_confidence="Low",
            min_btc_data_completeness=65,
            min_gold_data_completeness=45,
            allow_neutral_bias=True,
            exploratory_mode=True,
        )
    return PaperSignalConfig(
        profile="conservative",
        btc_long_score_threshold=70,
        btc_short_score_threshold=35,
        gold_long_score_threshold=70,
        gold_short_score_threshold=35,
        min_confidence="Medium",
        min_btc_data_completeness=80,
        min_gold_data_completeness=60,
        allow_neutral_bias=False,
        exploratory_mode=False,
    )
