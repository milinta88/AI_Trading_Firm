from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from analytics.trend_analyzer import TrendAnalyzer
from core.config import AppConfig
from core.models import DailyBriefContext, MarketDataPoint, WorkflowOutcome
from database.repository import WorkflowRepository
from reports.daily_report import DailyReportFormatter
from services.market_data_service import MarketDataService
from services.telegram_service import TelegramService

logger = logging.getLogger(__name__)


class OrchestratorBot:
    """Coordinates the Phase 1 daily brief workflow."""

    def __init__(
        self,
        config: AppConfig,
        repository: WorkflowRepository,
        gold_bot,
        btc_bot,
        data_quality_bot,
        risk_bot,
        report_formatter: DailyReportFormatter,
        market_data_service: MarketDataService,
        telegram_service: TelegramService,
        trend_analyzer: TrendAnalyzer,
        research_readiness_analyzer,
        strategy_hypothesis_engine,
        hypothesis_outcome_evaluator,
        hypothesis_review_analyzer,
        hypothesis_edge_slicing_analyzer,
    ) -> None:
        self.config = config
        self.repository = repository
        self.gold_bot = gold_bot
        self.btc_bot = btc_bot
        self.data_quality_bot = data_quality_bot
        self.risk_bot = risk_bot
        self.report_formatter = report_formatter
        self.market_data_service = market_data_service
        self.telegram_service = telegram_service
        self.trend_analyzer = trend_analyzer
        self.research_readiness_analyzer = research_readiness_analyzer
        self.strategy_hypothesis_engine = strategy_hypothesis_engine
        self.hypothesis_outcome_evaluator = hypothesis_outcome_evaluator
        self.hypothesis_review_analyzer = hypothesis_review_analyzer
        self.hypothesis_edge_slicing_analyzer = hypothesis_edge_slicing_analyzer

    def run_daily_brief(self) -> WorkflowOutcome:
        run_date = datetime.now(ZoneInfo(self.config.timezone)).date()
        workflow_run_id = self.repository.create_workflow_run(run_date=run_date, mode=self.config.mode)
        logger.info("Workflow run %s started for %s.", workflow_run_id, run_date.isoformat())

        try:
            market_data = self.market_data_service.collect_market_data()
            self._store_market_data(workflow_run_id, market_data)
            trend_context = self.trend_analyzer.analyze_all()

            gold_result = self.gold_bot.analyze(run_date, market_data=market_data, trend_context=trend_context)
            self.repository.store_analysis_result(workflow_run_id, self.gold_bot.name, gold_result)
            self.repository.store_score_snapshot(workflow_run_id, gold_result)

            btc_result = self.btc_bot.analyze(run_date, market_data=market_data, trend_context=trend_context)
            self.repository.store_analysis_result(workflow_run_id, self.btc_bot.name, btc_result)
            self.repository.store_score_snapshot(workflow_run_id, btc_result)

            data_quality = self.data_quality_bot.evaluate(market_data)
            risk_status = self.risk_bot.evaluate(
                gold_result=gold_result,
                btc_result=btc_result,
                data_quality_report=data_quality,
            )
            self.repository.store_risk_status(workflow_run_id, risk_status)
            research_readiness = self.research_readiness_analyzer.analyze_all()
            for readiness_result in research_readiness.values():
                self.repository.store_research_readiness_snapshot(workflow_run_id, readiness_result)
            strategy_hypotheses = self.strategy_hypothesis_engine.generate_all(
                score_results={
                    "Gold": gold_result,
                    "BTC": btc_result,
                },
                research_readiness=research_readiness,
                trend_context=trend_context,
                market_data=market_data,
                data_quality=data_quality,
            )
            for hypothesis in strategy_hypotheses.values():
                self.repository.store_strategy_hypothesis(workflow_run_id, hypothesis)
            hypothesis_outcomes = self.hypothesis_outcome_evaluator.evaluate_pending()
            for outcome in hypothesis_outcomes:
                self.repository.store_strategy_hypothesis_outcome(outcome)
            latest_hypothesis_outcomes = self.hypothesis_outcome_evaluator.load_recent(limit=8)
            hypothesis_review_summary = self.hypothesis_review_analyzer.build_summary()
            if self.config.hypothesis_review.enabled:
                self.repository.store_hypothesis_review_summary(hypothesis_review_summary)
            hypothesis_edge_slice_summary = self.hypothesis_edge_slicing_analyzer.build_summary()
            if self.config.hypothesis_edge_slicing.enabled:
                self.repository.store_hypothesis_edge_slice_summary(hypothesis_edge_slice_summary)

            report_context = DailyBriefContext(
                run_date=run_date,
                mode=self.config.mode,
                macro_regime=self._derive_macro_regime(gold_result.bias, btc_result.bias),
                gold=gold_result,
                btc=btc_result,
                market_data=market_data,
                data_quality=data_quality,
                risk=risk_status,
                system_health=self._build_system_health(market_data),
                trend_context=trend_context,
                research_readiness=research_readiness,
                strategy_hypotheses=strategy_hypotheses,
                hypothesis_outcomes=latest_hypothesis_outcomes,
                hypothesis_review_summary=hypothesis_review_summary,
                hypothesis_edge_slice_summary=hypothesis_edge_slice_summary,
            )
            report_text = self.report_formatter.format(report_context)

            delivery_result = self.telegram_service.send_message(report_text)
            self.repository.store_outbound_message(
                workflow_run_id=workflow_run_id,
                channel="telegram",
                status=delivery_result.status,
                recipient=delivery_result.recipient,
                message=report_text,
                error_message=delivery_result.detail if not delivery_result.success else None,
            )

            summary = (
                f"Gold {gold_result.bias} ({gold_result.score}), "
                f"BTC {btc_result.bias} ({btc_result.score}), "
                f"Risk {risk_status.status}"
            )
            final_status = "COMPLETED" if delivery_result.success else "COMPLETED_WITH_ALERTS"
            self.repository.complete_workflow_run(
                workflow_run_id=workflow_run_id,
                status=final_status,
                summary=summary,
                report_text=report_text,
                error_message=delivery_result.detail if not delivery_result.success else None,
            )
            logger.info("Workflow run %s finished with status %s.", workflow_run_id, final_status)

            return WorkflowOutcome(
                workflow_run_id=workflow_run_id,
                report_text=report_text,
                delivery=delivery_result,
            )
        except Exception as exc:
            logger.exception("Workflow run %s failed.", workflow_run_id)
            self.repository.complete_workflow_run(
                workflow_run_id=workflow_run_id,
                status="FAILED",
                summary="Daily brief workflow failed.",
                report_text="",
                error_message=str(exc),
            )
            raise

    def run_telegram_test(self) -> WorkflowOutcome:
        run_timestamp = datetime.now(ZoneInfo(self.config.timezone))
        workflow_run_id = self.repository.create_workflow_run(
            run_date=run_timestamp.date(),
            mode=f"{self.config.mode}_telegram_test",
        )
        logger.info("Telegram test workflow run %s started.", workflow_run_id)

        try:
            report_text = self._build_telegram_test_message(run_timestamp)
            delivery_result = self.telegram_service.send_message(report_text)
            self.repository.store_outbound_message(
                workflow_run_id=workflow_run_id,
                channel="telegram",
                status=delivery_result.status,
                recipient=delivery_result.recipient,
                message=report_text,
                error_message=delivery_result.detail if not delivery_result.success else None,
            )

            final_status = "COMPLETED" if delivery_result.success else "COMPLETED_WITH_ALERTS"
            summary = f"Telegram test finished with {delivery_result.status}."
            self.repository.complete_workflow_run(
                workflow_run_id=workflow_run_id,
                status=final_status,
                summary=summary,
                report_text=report_text,
                error_message=delivery_result.detail if not delivery_result.success else None,
            )
            logger.info("Telegram test workflow run %s finished with status %s.", workflow_run_id, final_status)

            return WorkflowOutcome(
                workflow_run_id=workflow_run_id,
                report_text=report_text,
                delivery=delivery_result,
            )
        except Exception as exc:
            logger.exception("Telegram test workflow run %s failed.", workflow_run_id)
            self.repository.complete_workflow_run(
                workflow_run_id=workflow_run_id,
                status="FAILED",
                summary="Telegram test workflow failed.",
                report_text="",
                error_message=str(exc),
            )
            raise

    def _build_system_health(self, market_data: dict[str, MarketDataPoint]) -> dict[str, str]:
        return {
            "SQLite": "OK",
            "BTC public data": market_data["btc_price"].status,
            "Fear & Greed": market_data["btc_fear_greed"].status,
            "BTC derivatives data": self._aggregate_status(
                [
                    market_data["btc_funding_rate"].status,
                    market_data["btc_open_interest"].status,
                ]
            ),
            "FRED": self._aggregate_fred_status(
                [
                    market_data["gold_us10y"].status,
                    market_data["gold_real_yield"].status,
                    market_data["gold_fed_funds"].status,
                    market_data["gold_cpi"].status,
                ]
            ),
            "Gold macro data": self._aggregate_status(
                [
                    market_data["gold_fed_funds"].status,
                    market_data["gold_cpi"].status,
                    market_data["gold_dxy"].status,
                    market_data["gold_us10y"].status,
                    market_data["gold_real_yield"].status,
                    market_data["gold_spot_price"].status,
                ]
            ),
            "MT5": "NOT_CONFIGURED",
            "Exchange private API": "NOT_CONFIGURED",
            "Telegram": self.telegram_service.mode_label,
        }

    def _build_telegram_test_message(self, run_timestamp: datetime) -> str:
        return "\n".join(
            [
                f"{self.config.app_name} Telegram Test",
                f"Timestamp: {run_timestamp.isoformat(timespec='seconds')}",
                f"Mode: {self.config.mode.title()}",
                "Execution: Disabled (MVP Phase 1)",
                "Purpose: Validate the Telegram reporting path without any trading logic.",
            ]
        )

    def _store_market_data(self, workflow_run_id: int, market_data: dict[str, MarketDataPoint]) -> None:
        for snapshot in market_data.values():
            self.repository.store_market_snapshot(workflow_run_id, snapshot)

    @staticmethod
    def _aggregate_status(statuses: list[str]) -> str:
        if all(status == "OK" for status in statuses):
            return "OK"
        if all(status == "NOT_CONFIGURED" for status in statuses):
            return "NOT_CONFIGURED"
        if any(status in {"FAIL", "NOT_AVAILABLE"} for status in statuses):
            return "WARNING"
        if any(status == "STALE" for status in statuses):
            return "WARNING"
        if any(status == "NOT_CONFIGURED" for status in statuses):
            return "WARNING"
        return "UNKNOWN"

    @staticmethod
    def _aggregate_fred_status(statuses: list[str]) -> str:
        if all(status == "OK" for status in statuses):
            return "OK"
        if all(status == "NOT_CONFIGURED" for status in statuses):
            return "NOT_CONFIGURED"
        if any(status == "STALE" for status in statuses):
            return "WARNING"
        if any(status in {"FAIL", "NOT_AVAILABLE"} for status in statuses):
            return "FAIL"
        if any(status == "NOT_CONFIGURED" for status in statuses):
            return "WARNING"
        return "WARNING"

    @staticmethod
    def _derive_macro_regime(gold_bias: str, btc_bias: str) -> str:
        if gold_bias == "Bullish" and btc_bias == "Bullish":
            return "Risk-on"
        if gold_bias == "Bearish" and btc_bias == "Bearish":
            return "Risk-off"
        return "Neutral"
