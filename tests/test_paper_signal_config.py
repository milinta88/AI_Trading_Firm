from __future__ import annotations

from pathlib import Path

import pytest

from core.config import ConfigValidationError, load_config


def test_load_config_applies_balanced_profile_presets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(
        tmp_path,
        paper_signal_lines=[
            "paper_signal:",
            "  profile: balanced",
        ],
    )
    _clear_env(monkeypatch)

    config = load_config(tmp_path)

    assert config.paper_signal.profile == "balanced"
    assert config.paper_signal.btc_long_score_threshold == 67
    assert config.paper_signal.btc_short_score_threshold == 38
    assert config.paper_signal.gold_long_score_threshold == 67
    assert config.paper_signal.gold_short_score_threshold == 38
    assert config.paper_signal.min_confidence == "Medium"
    assert config.paper_signal.min_btc_data_completeness == 75
    assert config.paper_signal.min_gold_data_completeness == 55
    assert config.paper_signal.allow_neutral_bias is False
    assert config.paper_signal.exploratory_mode is False


def test_load_config_rejects_invalid_paper_signal_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(
        tmp_path,
        paper_signal_lines=[
            "paper_signal:",
            "  profile: invalid-profile",
        ],
    )
    _clear_env(monkeypatch)

    with pytest.raises(ConfigValidationError):
        load_config(tmp_path)


def _write_config(tmp_path: Path, paper_signal_lines: list[str]) -> None:
    (tmp_path / "config.yaml").write_text(
        "\n".join(
            [
                "app:",
                "  name: AI Trading Firm",
                "  mode: research",
                "  timezone: Asia/Bangkok",
                "database:",
                "  path: data/database.db",
                "logging:",
                "  level: INFO",
                "  file_path: data/logs/test.log",
                "telegram:",
                "  timeout_seconds: 10",
                "  dry_run_if_missing_credentials: true",
                "market_data:",
                "  timeout_seconds: 10",
                "  btc_public_price_url: https://api.binance.com/api/v3/ticker/price",
                "  fear_and_greed_url: https://api.alternative.me/fng/",
                "btc_derivatives:",
                "  symbol: BTCUSDT",
                "  funding_rate_url: https://fapi.binance.com/fapi/v1/premiumIndex",
                "  open_interest_url: https://fapi.binance.com/fapi/v1/openInterest",
                "fred:",
                "  base_url: https://api.stlouisfed.org/fred/series/observations",
                "  timeout_seconds: 10",
                "  series:",
                "    gold_us10y:",
                "      series_id: DGS10",
                "      data_type: us10y",
                "      display_name: US10Y",
                "      stale_after_days: 10",
                "risk:",
                "  max_daily_loss_pct: 1.0",
                "  max_weekly_loss_pct: 3.0",
                "  execution_enabled: false",
                "paper_trading:",
                "  enabled: false",
                "  starting_equity: 10000",
                "  base_currency: USD",
                "  max_risk_per_trade_pct: 0.25",
                "  max_daily_loss_pct: 1.0",
                "  max_open_positions: 2",
                "  allow_long: true",
                "  allow_short: true",
                "  fill_mode: close_price",
                *paper_signal_lines,
            ]
        ),
        encoding="utf-8",
    )


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
