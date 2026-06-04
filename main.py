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
from analytics.hypothesis_edge_slicing import HypothesisEdgeSlicingAnalyzer
from analytics.hypothesis_outcomes import HypothesisOutcomeEvaluator
from analytics.hypothesis_review import HypothesisReviewAnalyzer
from analytics.hypothesis_review_export import HypothesisReviewExportService
from analytics.research_readiness import ResearchReadinessAnalyzer
from analytics.strategy_hypothesis import StrategyHypothesisEngine
from analytics.trend_analyzer import TrendAnalyzer
from agents.risk_officer_bot import RiskOfficerBot
from core.config import AppConfig, RuntimeOptions, TelegramRuntimeSettings, load_config, resolve_telegram_runtime
from core.logging_config import setup_logging
from database.init_db import initialize_database
from database.repository import WorkflowRepository
from paper_trading.analytics import PaperAnalytics
from paper_trading.export_service import PaperTradingExportService
from paper_trading.paper_orchestrator import build_paper_trading_orchestrator
from paper_trading.repository import PaperTradingRepository
from reports.daily_report import DailyReportFormatter
from reports.paper_report import PaperTradingReportFormatter
from services.dxy_service import DxyService
from services.fred_service import FredService
from services.gold_spot_service import GoldSpotService
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
    parser.add_argument(
        "--paper-export",
        action="store_true",
        help="Export local paper review CSV files to data/exports without running any workflow or simulation.",
    )
    parser.add_argument(
        "--hypothesis-outcomes",
        action="store_true",
        help="Evaluate matured persisted strategy hypotheses against later persisted market snapshots only.",
    )
    parser.add_argument(
        "--hypothesis-review",
        action="store_true",
        help="Build read-only hypothesis review analytics from persisted hypothesis outcomes only.",
    )
    parser.add_argument(
        "--hypothesis-review-export",
        action="store_true",
        help="Export persisted hypothesis review CSV files to data/exports without running any workflow or simulation.",
    )
    parser.add_argument(
        "--hypothesis-edge-slicing",
        action="store_true",
        help="Build read-only hypothesis edge slicing analytics from persisted hypothesis outcomes only.",
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
    gold_spot_service = GoldSpotService(config.gold_spot_provider)
    dxy_service = DxyService(config.dxy_provider)
    market_data_service = MarketDataService(
        timeout_seconds=config.market_data_timeout_seconds,
        btc_public_price_url=config.btc_public_price_url,
        fear_and_greed_url=config.fear_and_greed_url,
        btc_derivatives_symbol=config.btc_derivatives_symbol,
        btc_funding_rate_url=config.btc_funding_rate_url,
        btc_open_interest_url=config.btc_open_interest_url,
        fred_service=fred_service,
        gold_spot_service=gold_spot_service,
        dxy_service=dxy_service,
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
        research_readiness_analyzer=ResearchReadinessAnalyzer(
            database_path=config.database_path,
            config=config.research_readiness,
        ),
        strategy_hypothesis_engine=StrategyHypothesisEngine(
            config=config.strategy_hypotheses,
        ),
        hypothesis_outcome_evaluator=HypothesisOutcomeEvaluator(
            config=config.hypothesis_outcomes,
            database_path=config.database_path,
        ),
        hypothesis_review_analyzer=HypothesisReviewAnalyzer(
            database_path=config.database_path,
            config=config.hypothesis_review,
            lookback_days=config.hypothesis_outcomes.max_lookback_days,
        ),
        hypothesis_edge_slicing_analyzer=HypothesisEdgeSlicingAnalyzer(
            database_path=config.database_path,
            config=config.hypothesis_edge_slicing,
            readiness_buckets=config.hypothesis_review.readiness_buckets,
        ),
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
    fred_series = getattr(config, "fred_series", {})
    fred_api_key = getattr(config, "fred_api_key", None)
    gold_spot_provider = getattr(config, "gold_spot_provider", None)

    if fred_series and not fred_api_key:
        logger.warning(
            "FRED_API_KEY is missing. Gold FRED macro inputs will remain NOT_CONFIGURED until the key is added to the environment."
        )
    if (
        gold_spot_provider is not None
        and getattr(gold_spot_provider, "enabled", False)
        and not getattr(gold_spot_provider, "api_key", None)
    ):
        logger.warning(
            "%s is missing. Gold spot provider '%s' will remain NOT_CONFIGURED until the key is added to the environment.",
            getattr(gold_spot_provider, "api_key_env", "GOLD_API_KEY"),
            getattr(gold_spot_provider, "provider", "gold_api"),
        )
    if args.paper_report:
        logger.info("Loading local paper trading analytics report.")
        try:
            print(build_paper_report(config))
            return 0
        except Exception:
            logger.exception("Paper trading report failed.")
            return 1
    if args.paper_export:
        logger.info("Exporting local paper review CSV files.")
        try:
            for export_path in export_paper_review_files(config, project_root):
                print(export_path)
            return 0
        except Exception:
            logger.exception("Paper trading review export failed.")
            return 1
    if args.hypothesis_outcomes:
        logger.info("Evaluating persisted strategy hypothesis outcomes.")
        try:
            initialize_database(config.database_path)
            print(evaluate_hypothesis_outcomes(config))
            return 0
        except Exception:
            logger.exception("Strategy hypothesis outcome evaluation failed.")
            return 1
    if args.hypothesis_review:
        logger.info("Building hypothesis review analytics.")
        try:
            initialize_database(config.database_path)
            print(build_hypothesis_review_report(config))
            return 0
        except Exception:
            logger.exception("Hypothesis review analytics failed.")
            return 1
    if args.hypothesis_review_export:
        logger.info("Exporting local hypothesis review CSV files.")
        try:
            initialize_database(config.database_path)
            for export_path in export_hypothesis_review_files(config, project_root):
                print(export_path)
            return 0
        except Exception:
            logger.exception("Hypothesis review export failed.")
            return 1
    if args.hypothesis_edge_slicing:
        logger.info("Building hypothesis edge slicing analytics.")
        try:
            initialize_database(config.database_path)
            print(build_hypothesis_edge_slicing_report(config))
            return 0
        except Exception:
            logger.exception("Hypothesis edge slicing analytics failed.")
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
    research_readiness = ResearchReadinessAnalyzer(
        database_path=config.database_path,
        config=config.research_readiness,
    ).analyze_all()
    formatter = PaperTradingReportFormatter()
    strategy_hypotheses = StrategyHypothesisEngine(
        config=config.strategy_hypotheses,
        database_path=config.database_path,
    ).load_latest()
    hypothesis_outcomes = HypothesisOutcomeEvaluator(
        config=config.hypothesis_outcomes,
        database_path=config.database_path,
    ).load_recent(limit=8)
    hypothesis_review_analyzer = HypothesisReviewAnalyzer(
        database_path=config.database_path,
        config=config.hypothesis_review,
        lookback_days=config.hypothesis_outcomes.max_lookback_days,
    )
    hypothesis_review_summary = hypothesis_review_analyzer.load_latest_summary()
    if hypothesis_review_summary is None and config.hypothesis_review.enabled:
        hypothesis_review_summary = hypothesis_review_analyzer.build_summary()
    hypothesis_edge_slicing_analyzer = HypothesisEdgeSlicingAnalyzer(
        database_path=config.database_path,
        config=config.hypothesis_edge_slicing,
        readiness_buckets=config.hypothesis_review.readiness_buckets,
    )
    hypothesis_edge_slice_summary = hypothesis_edge_slicing_analyzer.load_latest_summary()
    if hypothesis_edge_slice_summary is None and config.hypothesis_edge_slicing.enabled:
        hypothesis_edge_slice_summary = hypothesis_edge_slicing_analyzer.build_summary()
    return formatter.format(
        analytics,
        paper_signal_summary=asdict(config.paper_signal),
        research_readiness=research_readiness,
        strategy_hypotheses=strategy_hypotheses,
        hypothesis_outcomes=hypothesis_outcomes,
        hypothesis_review_summary=hypothesis_review_summary,
        hypothesis_edge_slice_summary=hypothesis_edge_slice_summary,
    )


def export_paper_review_files(config: AppConfig, project_root: Path) -> list[Path]:
    export_service = PaperTradingExportService(
        database_path=config.database_path,
        starting_equity=config.paper_trading.starting_equity,
    )
    export_dir = project_root / "data" / "exports"
    return [
        artifact.path
        for artifact in export_service.write_review_exports(export_dir)
    ]


def export_hypothesis_review_files(config: AppConfig, project_root: Path) -> list[Path]:
    export_service = HypothesisReviewExportService(config.database_path)
    export_dir = project_root / "data" / "exports"
    return [
        artifact.path
        for artifact in export_service.write_review_exports(export_dir)
    ]


def evaluate_hypothesis_outcomes(config: AppConfig) -> str:
    evaluator = HypothesisOutcomeEvaluator(
        config=config.hypothesis_outcomes,
        database_path=config.database_path,
    )
    repository = WorkflowRepository(config.database_path)
    outcomes = evaluator.evaluate_pending()
    for outcome in outcomes:
        repository.store_strategy_hypothesis_outcome(outcome)

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.outcome_status] = counts.get(outcome.outcome_status, 0) + 1

    lines = [
        "STRATEGY HYPOTHESIS OUTCOME REVIEW",
        "READ-ONLY",
        "NO REAL EXECUTION",
        "",
        f"Evaluated Outcomes: {len(outcomes)}",
        f"Favorable: {counts.get('FAVORABLE', 0)}",
        f"Unfavorable: {counts.get('UNFAVORABLE', 0)}",
        f"Neutral: {counts.get('NEUTRAL', 0)}",
        f"Insufficient Follow-Up Data: {counts.get('INSUFFICIENT_FOLLOWUP_DATA', 0)}",
        f"Blocked Not Evaluated: {counts.get('BLOCKED_NOT_EVALUATED', 0)}",
    ]
    if outcomes:
        lines.extend(["", "Latest Evaluated Outcomes:"])
        for outcome in outcomes[:8]:
            move_label = "N/A" if outcome.move_pct is None else f"{outcome.move_pct:+.2f}%"
            lines.append(
                f"- {outcome.asset} | {outcome.strategy_family} | {outcome.horizon_hours}h | "
                f"{outcome.outcome_status} | Move {move_label}"
            )
    else:
        lines.extend(
            [
                "",
                "No matured strategy hypothesis outcomes were eligible for evaluation yet.",
            ]
        )
    return "\n".join(lines)


def build_hypothesis_review_report(config: AppConfig) -> str:
    analyzer = HypothesisReviewAnalyzer(
        database_path=config.database_path,
        config=config.hypothesis_review,
        lookback_days=config.hypothesis_outcomes.max_lookback_days,
    )
    summary = analyzer.build_summary()
    repository = WorkflowRepository(config.database_path)
    if config.hypothesis_review.enabled:
        repository.store_hypothesis_review_summary(summary)
    edge_analyzer = HypothesisEdgeSlicingAnalyzer(
        database_path=config.database_path,
        config=config.hypothesis_edge_slicing,
        readiness_buckets=config.hypothesis_review.readiness_buckets,
    )
    edge_summary = edge_analyzer.build_summary()
    if config.hypothesis_edge_slicing.enabled:
        repository.store_hypothesis_edge_slice_summary(edge_summary)

    lines = [
        "HYPOTHESIS REVIEW ANALYTICS",
        "REVIEW ONLY",
        "NO TRADING",
        "",
        f"Lookback Days: {summary.lookback_days}",
        f"Total Outcomes: {summary.total_outcomes}",
        f"Evaluated Outcomes: {summary.evaluated_outcomes}",
        f"Favorable: {summary.favorable_count}",
        f"Unfavorable: {summary.unfavorable_count}",
        f"Neutral: {summary.neutral_count}",
        f"Insufficient Follow-Up Data: {summary.insufficient_followup_count}",
        f"Blocked Not Evaluated: {summary.blocked_not_evaluated_count}",
        f"Favorable Rate: {summary.favorable_rate:.2%}",
        f"Unfavorable Rate: {summary.unfavorable_rate:.2%}",
        f"Neutral Rate: {summary.neutral_rate:.2%}",
    ]
    if summary.promoted_candidates:
        lines.extend(["", "Review Candidates:"])
        for candidate in summary.promoted_candidates[:10]:
            lines.append(
                f"- {candidate['strategy_family']} | Asset {candidate['asset']} | "
                f"Evaluated {candidate['evaluated_outcomes']} | Favorable {candidate['favorable_rate']:.2%}"
            )
    if summary.candidate_progress:
        lines.extend(["", "Candidate Progress:"])
        for candidate in summary.candidate_progress[:10]:
            lines.append(
                f"- {candidate['strategy_family']} | Asset {candidate['asset']} | "
                f"{candidate['candidate_status']} | n={candidate['evaluated_outcomes']}/"
                f"{candidate['required_min_outcomes']} | fav={candidate['favorable_rate']:.2%}/"
                f"{candidate['required_favorable_rate']:.2%} | unfav={candidate['unfavorable_rate']:.2%}/"
                f"{candidate['max_unfavorable_rate']:.2%} | adverse={_format_optional_pct(candidate['avg_adverse_move'])}/"
                f"{candidate['max_allowed_adverse_move']:.2f}%"
            )
    if summary.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in summary.warnings[:10])
    if not summary.promoted_candidates and summary.blocked_candidates:
        lines.extend(["", "Blocked Candidates:"])
        for candidate in summary.blocked_candidates[:10]:
            lines.append(
                f"- {candidate['strategy_family']} | Asset {candidate['asset']} | {candidate['reason']}"
            )
    lines.extend(["", *build_hypothesis_edge_slicing_lines(edge_summary)])
    return "\n".join(lines)


def build_hypothesis_edge_slicing_report(config: AppConfig) -> str:
    analyzer = HypothesisEdgeSlicingAnalyzer(
        database_path=config.database_path,
        config=config.hypothesis_edge_slicing,
        readiness_buckets=config.hypothesis_review.readiness_buckets,
    )
    summary = analyzer.build_summary()
    repository = WorkflowRepository(config.database_path)
    if config.hypothesis_edge_slicing.enabled:
        repository.store_hypothesis_edge_slice_summary(summary)
    return "\n".join(build_hypothesis_edge_slicing_lines(summary))


def build_hypothesis_edge_slicing_lines(summary) -> list[str]:
    lines = [
        "HYPOTHESIS EDGE SLICING",
        "REVIEW ONLY",
        "NO TRADING",
        "",
        f"Lookback Days: {summary.lookback_days}",
        f"Total Slices: {summary.total_slices}",
        f"Strongest Slices: {len(summary.strongest_slices)}",
        f"Weakest Slices: {len(summary.weakest_slices)}",
        f"Unstable Slices: {len(summary.unstable_slices)}",
    ]
    if summary.strongest_slices:
        lines.extend(["", "Strongest Slices:"])
        for row in summary.strongest_slices[:5]:
            lines.append(
                f"- {row.asset} | {row.strategy_family} | {row.regime} | {row.horizon_hours}h | "
                f"{row.readiness_bucket}/{row.confidence_bucket} | {row.stability_status} | "
                f"fav={row.favorable_rate:.0%} | n={row.sample_size}"
            )
    if summary.weakest_slices:
        lines.extend(["", "Weakest Slices:"])
        for row in summary.weakest_slices[:5]:
            lines.append(
                f"- {row.asset} | {row.strategy_family} | {row.regime} | {row.horizon_hours}h | "
                f"{row.stability_status} | unfav={row.unfavorable_rate:.0%} | "
                f"adverse={_format_optional_pct(row.avg_max_adverse_move_pct)} | n={row.sample_size}"
            )
    if summary.unstable_slices:
        lines.extend(["", "Unstable / Sample-Limited Slices:"])
        for row in summary.unstable_slices[:5]:
            lines.append(
                f"- {row.asset} | {row.strategy_family} | {row.regime} | {row.horizon_hours}h | "
                f"{row.stability_status} | n={row.sample_size}"
            )
    lines.extend(
        [
            "",
            "Warnings:",
            "- REVIEW ONLY. No automatic promotion or trading occurs from edge slicing analytics.",
        ]
    )
    if summary.warnings:
        lines.extend(f"- {warning}" for warning in summary.warnings[:10])
    return lines


def _format_optional_pct(value: object) -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "N/A"


if __name__ == "__main__":
    raise SystemExit(main())
