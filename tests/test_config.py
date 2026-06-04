from __future__ import annotations

from pathlib import Path

import pytest

from core.config import ConfigValidationError, RuntimeOptions, load_config, resolve_telegram_runtime


def test_load_config_defaults_to_dry_run_without_telegram_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(tmp_path)
    _clear_telegram_env(monkeypatch)

    config = load_config(tmp_path)
    runtime = resolve_telegram_runtime(config, RuntimeOptions(send_telegram=True))

    assert config.telegram_is_configured is False
    assert config.strategy_hypotheses.enabled is True
    assert config.strategy_hypotheses.min_confidence == "Medium"
    assert config.hypothesis_outcomes.enabled is True
    assert config.hypothesis_outcomes.horizons_hours == [4, 24, 72]
    assert config.hypothesis_review.enabled is True
    assert config.hypothesis_review.min_favorable_rate_for_candidate == 0.55
    assert config.hypothesis_edge_slicing.enabled is True
    assert config.hypothesis_edge_slicing.lookback_days == 90
    assert config.telegram_status.mode == "DRY_RUN"
    assert runtime.mode == "DRY_RUN"
    assert runtime.allow_live_sends is False


def test_load_config_enables_live_telegram_when_credentials_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TELEGRAM_BOT_TOKEN=test-token",
                "TELEGRAM_CHAT_ID=123456",
                "FRED_API_KEY=test-fred-key",
                "APP_MODE=research",
                "LOG_LEVEL=INFO",
            ]
        ),
        encoding="utf-8",
    )
    _clear_telegram_env(monkeypatch)

    config = load_config(tmp_path)
    runtime = resolve_telegram_runtime(config)

    assert config.telegram_is_configured is True
    assert config.telegram_status.mode == "LIVE_READY"
    assert runtime.mode == "LIVE"
    assert runtime.allow_live_sends is True


def test_load_config_reads_gold_spot_api_key_from_configured_env_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_config(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "FRED_API_KEY=test-fred-key",
                "CUSTOM_GOLD_KEY=test-gold-key",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("CUSTOM_GOLD_KEY", raising=False)

    (tmp_path / "config.yaml").write_text(
        (tmp_path / "config.yaml").read_text(encoding="utf-8") + "\n"
        + "\n".join(
            [
                "gold_spot_provider:",
                "  enabled: true",
                "  provider: goldapi_io",
                "  url: https://example.com/gold",
                "  api_key_env: CUSTOM_GOLD_KEY",
                "  timeout_seconds: 10",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.gold_spot_provider.api_key_env == "CUSTOM_GOLD_KEY"
    assert config.gold_spot_provider.api_key == "test-gold-key"


def test_load_config_rejects_trade_execution_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(tmp_path, execution_enabled=True)
    _clear_telegram_env(monkeypatch)

    with pytest.raises(ConfigValidationError):
        load_config(tmp_path)


def test_load_config_applies_fred_stale_after_series_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_config(tmp_path)
    (tmp_path / "config.yaml").write_text(
        (tmp_path / "config.yaml").read_text(encoding="utf-8") + "\n"
        + "\n".join(
            [
                "fred:",
                "  base_url: https://api.stlouisfed.org/fred/series/observations",
                "  timeout_seconds: 10",
                "  stale_after_days_by_series:",
                "    gold_fed_funds: 75",
                "    gold_cpi: 75",
                "  series:",
                "    gold_us10y:",
                "      series_id: DGS10",
                "      data_type: us10y",
                "      display_name: US10Y",
                "      stale_after_days: 10",
                "    gold_real_yield:",
                "      series_id: DFII10",
                "      data_type: real_yield",
                "      display_name: Real Yield",
                "      stale_after_days: 10",
                "    gold_fed_funds:",
                "      series_id: FEDFUNDS",
                "      data_type: fed_funds",
                "      display_name: Fed Funds",
                "      stale_after_days: 45",
                "    gold_cpi:",
                "      series_id: CPIAUCSL",
                "      data_type: cpi",
                "      display_name: CPI",
                "      stale_after_days: 45",
            ]
        ),
        encoding="utf-8",
    )
    _clear_telegram_env(monkeypatch)

    config = load_config(tmp_path)

    assert config.fred_series["gold_fed_funds"].stale_after_days == 75
    assert config.fred_series["gold_cpi"].stale_after_days == 75


def _write_config(tmp_path: Path, execution_enabled: bool = False) -> None:
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
                "    gold_real_yield:",
                "      series_id: DFII10",
                "      data_type: real_yield",
                "      display_name: Real Yield",
                "      stale_after_days: 10",
                "    gold_fed_funds:",
                "      series_id: FEDFUNDS",
                "      data_type: fed_funds",
                "      display_name: Fed Funds",
                "      stale_after_days: 45",
                "    gold_cpi:",
                "      series_id: CPIAUCSL",
                "      data_type: cpi",
                "      display_name: CPI",
                "      stale_after_days: 45",
                "risk:",
                "  max_daily_loss_pct: 1.0",
                "  max_weekly_loss_pct: 3.0",
                f"  execution_enabled: {'true' if execution_enabled else 'false'}",
            ]
        ),
        encoding="utf-8",
    )


def _clear_telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
