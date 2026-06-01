from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback path is covered instead.
    load_dotenv = None

logger = logging.getLogger(__name__)

ALLOWED_APP_MODES = {"research", "paper", "live", "live_micro"}
ALLOWED_PAPER_SIGNAL_PROFILES = {"conservative", "balanced", "exploratory"}
ALLOWED_CONFIDENCE_LEVELS = {"Low", "Medium", "High"}

PAPER_SIGNAL_PROFILE_PRESETS: dict[str, dict[str, object]] = {
    "conservative": {
        "btc_long_score_threshold": 70,
        "btc_short_score_threshold": 35,
        "gold_long_score_threshold": 70,
        "gold_short_score_threshold": 35,
        "min_confidence": "Medium",
        "min_btc_data_completeness": 80,
        "min_gold_data_completeness": 60,
        "allow_neutral_bias": False,
        "exploratory_mode": False,
    },
    "balanced": {
        "btc_long_score_threshold": 67,
        "btc_short_score_threshold": 38,
        "gold_long_score_threshold": 67,
        "gold_short_score_threshold": 38,
        "min_confidence": "Medium",
        "min_btc_data_completeness": 75,
        "min_gold_data_completeness": 55,
        "allow_neutral_bias": False,
        "exploratory_mode": False,
    },
    "exploratory": {
        "btc_long_score_threshold": 62,
        "btc_short_score_threshold": 42,
        "gold_long_score_threshold": 62,
        "gold_short_score_threshold": 42,
        "min_confidence": "Low",
        "min_btc_data_completeness": 65,
        "min_gold_data_completeness": 45,
        "allow_neutral_bias": True,
        "exploratory_mode": True,
    },
}


class ConfigValidationError(ValueError):
    """Raised when the local configuration is invalid for Phase 1."""


@dataclass(frozen=True)
class TelegramConfigStatus:
    is_configured: bool
    mode: str
    reason: str


@dataclass(frozen=True)
class RuntimeOptions:
    dry_run: bool = False
    send_telegram: bool = False
    test_telegram: bool = False


@dataclass(frozen=True)
class TelegramRuntimeSettings:
    allow_live_sends: bool
    mode: str
    reason: str
    is_test_message: bool = False


@dataclass(frozen=True)
class FredSeriesConfig:
    key: str
    series_id: str
    data_type: str
    display_name: str
    stale_after_days: int


@dataclass(frozen=True)
class PaperTradingConfig:
    enabled: bool
    starting_equity: float
    base_currency: str
    max_risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_open_positions: int
    allow_long: bool
    allow_short: bool
    fill_mode: str


@dataclass(frozen=True)
class PaperSignalConfig:
    profile: str
    btc_long_score_threshold: int
    btc_short_score_threshold: int
    gold_long_score_threshold: int
    gold_short_score_threshold: int
    min_confidence: str
    min_btc_data_completeness: int
    min_gold_data_completeness: int
    allow_neutral_bias: bool
    exploratory_mode: bool

    @property
    def experimental_label(self) -> str:
        if self.profile == "exploratory" or self.exploratory_mode:
            return "EXPERIMENTAL / PAPER ONLY"
        return "PAPER ONLY"


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    app_name: str
    mode: str
    timezone: str
    database_path: Path
    log_level: str
    log_file_path: Path
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    telegram_timeout_seconds: int
    telegram_dry_run_if_missing_credentials: bool
    market_data_timeout_seconds: int
    btc_public_price_url: str
    fear_and_greed_url: str
    btc_derivatives_symbol: str
    btc_funding_rate_url: str
    btc_open_interest_url: str
    fred_api_key: str | None
    fred_base_url: str
    fred_timeout_seconds: int
    fred_series: dict[str, FredSeriesConfig]
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    execution_enabled: bool
    paper_trading: PaperTradingConfig
    paper_signal: PaperSignalConfig

    @property
    def telegram_status(self) -> TelegramConfigStatus:
        return validate_telegram_config(
            bot_token=self.telegram_bot_token,
            chat_id=self.telegram_chat_id,
        )

    @property
    def telegram_is_configured(self) -> bool:
        return self.telegram_status.is_configured


def load_config(project_root: Path) -> AppConfig:
    env_path = project_root / ".env"
    _load_env_file(env_path)

    config_path = project_root / "config.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle) or {}

    app_section = raw_config.get("app", {})
    database_section = raw_config.get("database", {})
    logging_section = raw_config.get("logging", {})
    telegram_section = raw_config.get("telegram", {})
    market_data_section = raw_config.get("market_data", {})
    btc_derivatives_section = raw_config.get("btc_derivatives", {})
    fred_section = raw_config.get("fred", {})
    risk_section = raw_config.get("risk", {})
    paper_trading_section = raw_config.get("paper_trading", {})
    paper_signal_section = raw_config.get("paper_signal", {})

    config = AppConfig(
        project_root=project_root,
        app_name=str(app_section.get("name", "AI Trading Firm")).strip(),
        mode=os.getenv("APP_MODE", str(app_section.get("mode", "research"))).strip().lower(),
        timezone=str(app_section.get("timezone", "UTC")).strip(),
        database_path=_resolve_path(project_root, str(database_section.get("path", "data/database.db"))),
        log_level=os.getenv("LOG_LEVEL", str(logging_section.get("level", "INFO"))).strip().upper(),
        log_file_path=_resolve_path(project_root, str(logging_section.get("file_path", "data/logs/ai_trading_firm.log"))),
        telegram_bot_token=_clean_optional_text(os.getenv("TELEGRAM_BOT_TOKEN")),
        telegram_chat_id=_clean_optional_text(os.getenv("TELEGRAM_CHAT_ID")),
        telegram_timeout_seconds=int(telegram_section.get("timeout_seconds", 10)),
        telegram_dry_run_if_missing_credentials=_as_bool(
            telegram_section.get("dry_run_if_missing_credentials", True)
        ),
        market_data_timeout_seconds=int(market_data_section.get("timeout_seconds", 10)),
        btc_public_price_url=str(
            market_data_section.get("btc_public_price_url", "https://api.binance.com/api/v3/ticker/price")
        ).strip(),
        fear_and_greed_url=str(
            market_data_section.get("fear_and_greed_url", "https://api.alternative.me/fng/")
        ).strip(),
        btc_derivatives_symbol=str(btc_derivatives_section.get("symbol", "BTCUSDT")).strip(),
        btc_funding_rate_url=str(
            btc_derivatives_section.get("funding_rate_url", "https://fapi.binance.com/fapi/v1/premiumIndex")
        ).strip(),
        btc_open_interest_url=str(
            btc_derivatives_section.get("open_interest_url", "https://fapi.binance.com/fapi/v1/openInterest")
        ).strip(),
        fred_api_key=_clean_optional_text(os.getenv("FRED_API_KEY")),
        fred_base_url=str(
            fred_section.get("base_url", "https://api.stlouisfed.org/fred/series/observations")
        ).strip(),
        fred_timeout_seconds=int(fred_section.get("timeout_seconds", 10)),
        fred_series=_build_fred_series_config(fred_section.get("series", {})),
        max_daily_loss_pct=float(risk_section.get("max_daily_loss_pct", 1.0)),
        max_weekly_loss_pct=float(risk_section.get("max_weekly_loss_pct", 3.0)),
        execution_enabled=_as_bool(risk_section.get("execution_enabled", False)),
        paper_trading=_build_paper_trading_config(paper_trading_section),
        paper_signal=_build_paper_signal_config(paper_signal_section),
    )

    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    errors: list[str] = []

    if not config.app_name:
        errors.append("app.name is required.")

    if not config.mode:
        errors.append("app.mode or APP_MODE is required.")
    elif config.mode not in ALLOWED_APP_MODES:
        allowed_modes = ", ".join(sorted(ALLOWED_APP_MODES))
        errors.append(f"app.mode must be one of: {allowed_modes}.")

    if not config.timezone:
        errors.append("app.timezone is required.")
    else:
        try:
            ZoneInfo(config.timezone)
        except ZoneInfoNotFoundError:
            errors.append(f"app.timezone '{config.timezone}' is not a valid IANA timezone.")

    if not str(config.database_path).strip():
        errors.append("database.path is required.")

    if not str(config.log_file_path).strip():
        errors.append("logging.file_path is required.")

    if config.telegram_timeout_seconds <= 0:
        errors.append("telegram.timeout_seconds must be greater than zero.")

    if config.market_data_timeout_seconds <= 0:
        errors.append("market_data.timeout_seconds must be greater than zero.")

    if not config.btc_public_price_url:
        errors.append("market_data.btc_public_price_url is required.")

    if not config.fear_and_greed_url:
        errors.append("market_data.fear_and_greed_url is required.")

    if not config.btc_derivatives_symbol:
        errors.append("btc_derivatives.symbol is required.")

    if not config.btc_funding_rate_url:
        errors.append("btc_derivatives.funding_rate_url is required.")

    if not config.btc_open_interest_url:
        errors.append("btc_derivatives.open_interest_url is required.")

    if config.fred_timeout_seconds <= 0:
        errors.append("fred.timeout_seconds must be greater than zero.")

    if not config.fred_base_url:
        errors.append("fred.base_url is required.")

    if not config.fred_series:
        errors.append("fred.series must define at least one configured series.")

    for key, series_config in config.fred_series.items():
        if not series_config.series_id:
            errors.append(f"fred.series.{key}.series_id is required.")
        if not series_config.data_type:
            errors.append(f"fred.series.{key}.data_type is required.")
        if series_config.stale_after_days <= 0:
            errors.append(f"fred.series.{key}.stale_after_days must be greater than zero.")

    if config.max_daily_loss_pct <= 0:
        errors.append("risk.max_daily_loss_pct must be greater than zero.")

    if config.max_weekly_loss_pct <= 0:
        errors.append("risk.max_weekly_loss_pct must be greater than zero.")

    if config.max_weekly_loss_pct < config.max_daily_loss_pct:
        errors.append("risk.max_weekly_loss_pct must be greater than or equal to risk.max_daily_loss_pct.")

    if config.execution_enabled:
        errors.append("risk.execution_enabled must remain false because real trade execution is disabled.")

    if config.paper_trading.starting_equity <= 0:
        errors.append("paper_trading.starting_equity must be greater than zero.")

    if not config.paper_trading.base_currency:
        errors.append("paper_trading.base_currency is required.")

    if config.paper_trading.max_risk_per_trade_pct <= 0:
        errors.append("paper_trading.max_risk_per_trade_pct must be greater than zero.")

    if config.paper_trading.max_daily_loss_pct <= 0:
        errors.append("paper_trading.max_daily_loss_pct must be greater than zero.")

    if config.paper_trading.max_open_positions < 0:
        errors.append("paper_trading.max_open_positions must be zero or greater.")

    if config.paper_trading.fill_mode not in {"close_price", "latest_price"}:
        errors.append("paper_trading.fill_mode must be close_price or latest_price.")

    if config.paper_signal.profile not in ALLOWED_PAPER_SIGNAL_PROFILES:
        allowed_profiles = ", ".join(sorted(ALLOWED_PAPER_SIGNAL_PROFILES))
        errors.append(f"paper_signal.profile must be one of: {allowed_profiles}.")

    if config.paper_signal.min_confidence not in ALLOWED_CONFIDENCE_LEVELS:
        allowed_confidence = ", ".join(sorted(ALLOWED_CONFIDENCE_LEVELS))
        errors.append(f"paper_signal.min_confidence must be one of: {allowed_confidence}.")

    for field_name, value in {
        "paper_signal.btc_long_score_threshold": config.paper_signal.btc_long_score_threshold,
        "paper_signal.btc_short_score_threshold": config.paper_signal.btc_short_score_threshold,
        "paper_signal.gold_long_score_threshold": config.paper_signal.gold_long_score_threshold,
        "paper_signal.gold_short_score_threshold": config.paper_signal.gold_short_score_threshold,
        "paper_signal.min_btc_data_completeness": config.paper_signal.min_btc_data_completeness,
        "paper_signal.min_gold_data_completeness": config.paper_signal.min_gold_data_completeness,
    }.items():
        if value < 0 or value > 100:
            errors.append(f"{field_name} must be between 0 and 100.")

    if config.paper_signal.btc_short_score_threshold > config.paper_signal.btc_long_score_threshold:
        errors.append("paper_signal.btc_short_score_threshold must be less than or equal to paper_signal.btc_long_score_threshold.")

    if config.paper_signal.gold_short_score_threshold > config.paper_signal.gold_long_score_threshold:
        errors.append("paper_signal.gold_short_score_threshold must be less than or equal to paper_signal.gold_long_score_threshold.")

    if errors:
        raise ConfigValidationError(" ".join(errors))


def validate_telegram_config(bot_token: str | None, chat_id: str | None) -> TelegramConfigStatus:
    missing_fields: list[str] = []
    if not bot_token:
        missing_fields.append("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        missing_fields.append("TELEGRAM_CHAT_ID")

    if missing_fields:
        missing_csv = ", ".join(missing_fields)
        return TelegramConfigStatus(
            is_configured=False,
            mode="DRY_RUN",
            reason=f"Missing {missing_csv}; Telegram delivery stays in DRY_RUN mode.",
        )

    return TelegramConfigStatus(
        is_configured=True,
        mode="LIVE_READY",
        reason="Telegram credentials loaded from environment; live delivery is available.",
    )


def resolve_telegram_runtime(config: AppConfig, options: RuntimeOptions | None = None) -> TelegramRuntimeSettings:
    options = options or RuntimeOptions()
    telegram_status = config.telegram_status

    if options.dry_run:
        reason = "CLI override (--dry-run) forced Telegram delivery into DRY_RUN mode."
        return TelegramRuntimeSettings(
            allow_live_sends=False,
            mode="DRY_RUN",
            reason=reason,
            is_test_message=options.test_telegram,
        )

    if telegram_status.is_configured:
        if options.test_telegram:
            reason = "Telegram credentials are present; a live Telegram test message will be sent."
        elif options.send_telegram:
            reason = "Telegram credentials are present; the daily brief will be sent live."
        else:
            reason = "Telegram credentials are present; the default daily brief will be sent live."

        return TelegramRuntimeSettings(
            allow_live_sends=True,
            mode="LIVE",
            reason=reason,
            is_test_message=options.test_telegram,
        )

    reason = telegram_status.reason
    if options.send_telegram:
        reason = f"{reason} --send-telegram was requested, but the app will stay in DRY_RUN mode."
    elif options.test_telegram:
        reason = f"{reason} --test-telegram was requested, but the test message will stay in DRY_RUN mode."

    return TelegramRuntimeSettings(
        allow_live_sends=False,
        mode="DRY_RUN",
        reason=reason,
        is_test_message=options.test_telegram,
    )


def _resolve_path(project_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return project_root / path


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        logger.info("No .env file found at %s. Using existing process environment only.", env_path)
        return

    if load_dotenv is not None:
        load_dotenv(dotenv_path=env_path, override=False)
        logger.info("Loaded environment variables from %s using python-dotenv.", env_path.name)
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

    logger.info(
        "Loaded environment variables from %s using the fallback parser because python-dotenv is unavailable.",
        env_path.name,
    )


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip().strip("\"'")
    return cleaned or None


def _build_fred_series_config(raw_series: object) -> dict[str, FredSeriesConfig]:
    if not isinstance(raw_series, dict):
        return {}

    configured_series: dict[str, FredSeriesConfig] = {}
    for key, value in raw_series.items():
        if not isinstance(value, dict):
            continue

        configured_series[str(key)] = FredSeriesConfig(
            key=str(key),
            series_id=str(value.get("series_id", "")).strip(),
            data_type=str(value.get("data_type", "")).strip(),
            display_name=str(value.get("display_name", key)).strip(),
            stale_after_days=int(value.get("stale_after_days", 30)),
        )

    return configured_series


def _build_paper_trading_config(raw_config: object) -> PaperTradingConfig:
    section = raw_config if isinstance(raw_config, dict) else {}
    return PaperTradingConfig(
        enabled=_as_bool(section.get("enabled", False)),
        starting_equity=float(section.get("starting_equity", 10_000)),
        base_currency=str(section.get("base_currency", "USD")).strip() or "USD",
        max_risk_per_trade_pct=float(section.get("max_risk_per_trade_pct", 0.25)),
        max_daily_loss_pct=float(section.get("max_daily_loss_pct", 1.0)),
        max_open_positions=int(section.get("max_open_positions", 2)),
        allow_long=_as_bool(section.get("allow_long", True)),
        allow_short=_as_bool(section.get("allow_short", True)),
        fill_mode=str(section.get("fill_mode", "close_price")).strip() or "close_price",
    )


def _build_paper_signal_config(raw_config: object) -> PaperSignalConfig:
    section = raw_config if isinstance(raw_config, dict) else {}
    raw_profile = str(section.get("profile", "conservative")).strip().lower() or "conservative"
    preset = PAPER_SIGNAL_PROFILE_PRESETS.get(raw_profile, PAPER_SIGNAL_PROFILE_PRESETS["conservative"])

    return PaperSignalConfig(
        profile=raw_profile,
        btc_long_score_threshold=int(section.get("btc_long_score_threshold", preset["btc_long_score_threshold"])),
        btc_short_score_threshold=int(section.get("btc_short_score_threshold", preset["btc_short_score_threshold"])),
        gold_long_score_threshold=int(section.get("gold_long_score_threshold", preset["gold_long_score_threshold"])),
        gold_short_score_threshold=int(section.get("gold_short_score_threshold", preset["gold_short_score_threshold"])),
        min_confidence=_clean_confidence(str(section.get("min_confidence", preset["min_confidence"]))),
        min_btc_data_completeness=int(
            section.get("min_btc_data_completeness", preset["min_btc_data_completeness"])
        ),
        min_gold_data_completeness=int(
            section.get("min_gold_data_completeness", preset["min_gold_data_completeness"])
        ),
        allow_neutral_bias=_as_bool(section.get("allow_neutral_bias", preset["allow_neutral_bias"])),
        exploratory_mode=_as_bool(section.get("exploratory_mode", preset["exploratory_mode"])),
    )


def _clean_confidence(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "low":
        return "Low"
    if normalized == "medium":
        return "Medium"
    if normalized == "high":
        return "High"
    return value.strip()
