from __future__ import annotations

import argparse
import logging
from dataclasses import asdict
from datetime import date
from pathlib import Path

from agents.btc_fundamental_bot import BTCFundamentalBot
from agents.data_quality_bot import DataQualityBot
from agents.gold_fundamental_bot import GoldFundamentalBot
from agents.orchestrator_bot import OrchestratorBot
from analytics.trend_analyzer import TrendAnalyzer
from agents.risk_officer_bot import RiskOfficerBot
from core.config import AppConfig, RuntimeOptions, TelegramRuntimeSettings, load_config, resolve_telegram_runtime
from core.logging_config import setup_logging
from database.init_db import initialize_database
from database.repository import WorkflowRepository
from paper_trading.analytics import PaperAnalytics
from paper_trading.paper_orchestrator import build_paper_trading_orchestrator
from paper_trading.repository import PaperTradingRepository
from reports.daily_report import DailyReportFormatter
from reports.paper_report import PaperTradingReportFormatter
from services.fred_service import FredService
from services.market_data_service import MarketDataService
from services.telegram_service import TelegramService


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the AI Trading Firm research and simulated-paper workflows.")
    delivery_group = parser.add_mutually_exclusive_group()
    delivery_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the report but never send Telegram.",
    )
    delivery_group.add_argument(
        "--send-telegram",
        action="store_true",
        help="Send the daily brief to Telegram when credentials are available.",
    )
    delivery_group.add_argument(
        "--test-telegram",
        action="store_true",
        help="Send a short Telegram test message only.",
    )
    parser.add_argument(
        "--paper-run",
        action="store_true",
        help="Run the research workflow, then run simulated paper trading if paper_trading.enabled is true.",
    )
    parser.add_argument(
        "--paper-report",
        action="store_true",
        help="Print the latest local paper trading analytics summary without running any workflow or simulation.",
    )
    return parser.parse_args(argv)


def build_runtime_options(args: argparse.Namespace) -> RuntimeOptions:
    return RuntimeOptions(
        dry_run=args.dry_run,
        send_telegram=args.send_telegram,
        test_telegram=args.test_telegram,
    )


def build_orchestrator(config: AppConfig, telegram_runtime: TelegramRuntimeSettings) -> OrchestratorBot:
    repository = WorkflowRepository(config.database_path)
    fred_service = FredService(
        api_key=config.fred_api_key,
        base_url=config.fred_base_url,
        timeout_seconds=config.fred_timeout_seconds,
        series_configs=config.fred_series,
    )
    market_data_service = MarketDataService(
        timeout_seconds=config.market_data_timeout_seconds,
        btc_public_price_url=config.btc_public_price_url,
        fear_and_greed_url=config.fear_and_greed_url,
        btc_derivatives_symbol=config.btc_derivatives_symbol,
        btc_funding_rate_url=config.btc_funding_rate_url,
        btc_open_interest_url=config.btc_open_interest_url,
        fred_service=fred_service,
    )
    telegram_service = TelegramService(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        timeout_seconds=config.telegram_timeout_seconds,
        allow_live_sends=telegram_runtime.allow_live_sends,
        runtime_reason=telegram_runtime.reason,
    )

    return OrchestratorBot(
        config=config,
        repository=repository,
        gold_bot=GoldFundamentalBot(),
        btc_bot=BTCFundamentalBot(),
        data_quality_bot=DataQualityBot(),
        risk_bot=RiskOfficerBot(
            max_daily_loss_pct=config.max_daily_loss_pct,
            max_weekly_loss_pct=config.max_weekly_loss_pct,
            execution_enabled=config.execution_enabled,
        ),
        report_formatter=DailyReportFormatter(),
        market_data_service=market_data_service,
        telegram_service=telegram_service,
        trend_analyzer=TrendAnalyzer(config.database_path),
    )


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parent
    args = parse_args(argv)
    runtime_options = build_runtime_options(args)

    try:
        config = load_config(project_root)
        setup_logging(config)
    except Exception:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        )
        logging.exception("Application bootstrap failed.")
        return 1

    logger = logging.getLogger(__name__)
    if args.paper_report:
        logger.info("Loading local paper trading analytics report.")
        try:
            print(build_paper_report(config))
            return 0
        except Exception:
            logger.exception("Paper trading report failed.")
            return 1

    workflow_label = "Telegram test" if runtime_options.test_telegram else "daily brief"
    logger.info("Starting %s %s workflow in %s mode.", config.app_name, workflow_label, config.mode)
    telegram_runtime = resolve_telegram_runtime(config, runtime_options)
    logger.info("Telegram runtime mode: %s. %s", telegram_runtime.mode, telegram_runtime.reason)

    try:
        initialize_database(config.database_path)
        orchestrator = build_orchestrator(config, telegram_runtime)
        outcome = orchestrator.run_telegram_test() if runtime_options.test_telegram else orchestrator.run_daily_brief()
        logger.info(
            "Workflow run %s completed with delivery status %s.",
            outcome.workflow_run_id,
            outcome.delivery.status,
        )
        print(outcome.report_text)
        if args.paper_run:
            if runtime_options.test_telegram:
                message = "--paper-run was requested with --test-telegram; paper trading only runs after the daily brief workflow."
                logger.info(message)
                print(message)
            elif not config.paper_trading.enabled:
                message = "Paper trading disabled: paper_trading.enabled is false. No simulated orders were created."
                logger.info(message)
                print(message)
            else:
                paper_summary = run_paper_trading(config, outcome.workflow_run_id)
                print(paper_summary.to_text())
        return 0 if outcome.delivery.success else 1
    except Exception:
        logger.exception("Daily brief workflow failed.")
        return 1


def run_paper_trading(config: AppConfig, workflow_run_id: int):
    repository = PaperTradingRepository(config.database_path)
    orchestrator = build_paper_trading_orchestrator(
        config.paper_trading,
        config.paper_signal,
        repository,
    )
    run_date = date.today()
    return orchestrator.run(workflow_run_id=workflow_run_id, run_date=run_date)


def build_paper_report(config: AppConfig) -> str:
    analytics = PaperAnalytics(
        database_path=config.database_path,
        starting_equity=config.paper_trading.starting_equity,
    ).build_report()
    formatter = PaperTradingReportFormatter()
    return formatter.format(analytics, paper_signal_summary=asdict(config.paper_signal))


if __name__ == "__main__":
    raise SystemExit(main())
