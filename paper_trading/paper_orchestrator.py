from __future__ import annotations

import logging
from datetime import date

from core.config import PaperSignalConfig, PaperTradingConfig
from paper_trading.execution_simulator import PaperExecutionSimulator
from paper_trading.models import PaperRunSummary, PaperSignal, PaperSignalReview
from paper_trading.repository import PaperTradingRepository
from paper_trading.risk_engine import PaperRiskEngine
from paper_trading.signal_builder import PaperSignalBuilder

logger = logging.getLogger(__name__)


class PaperTradingOrchestrator:
    """Coordinates simulated-only paper trading after the research workflow."""

    def __init__(
        self,
        config: PaperTradingConfig,
        signal_config: PaperSignalConfig,
        repository: PaperTradingRepository,
        signal_builder: PaperSignalBuilder,
        risk_engine: PaperRiskEngine,
        execution_simulator: PaperExecutionSimulator,
    ) -> None:
        self.config = config
        self.signal_config = signal_config
        self.repository = repository
        self.signal_builder = signal_builder
        self.risk_engine = risk_engine
        self.execution_simulator = execution_simulator

    def run(self, workflow_run_id: int, run_date: date) -> PaperRunSummary:
        if not self.config.enabled:
            note = "paper_trading.enabled is false; no simulated orders were evaluated."
            logger.info(note)
            return PaperRunSummary(
                enabled=False,
                status="DISABLED",
                workflow_run_id=workflow_run_id,
                active_profile=self.signal_config.profile,
                notes=[note],
            )

        logger.info("Starting simulated-only paper trading run for workflow %s.", workflow_run_id)
        position_results = self.execution_simulator.update_open_positions(workflow_run_id)
        score_rows = self.repository.fetch_latest_score_snapshots()
        data_quality_status = self.repository.fetch_latest_data_quality()
        orders_opened = 0
        notes: list[str] = [
            "PAPER TRADE simulation only.",
            "No broker, MT5, exchange, or private trading endpoint is used.",
            f"Active paper signal profile: {self.signal_config.profile} ({self.signal_config.experimental_label}).",
        ]

        for score_row in score_rows:
            asset = str(score_row.get("asset", "UNKNOWN"))
            latest_price = self.repository.fetch_latest_market_price(asset)
            signal = self.signal_builder.build_signal(score_row, latest_price=latest_price)
            if not signal.is_trade_candidate:
                self.repository.store_signal_review(
                    _build_signal_review(
                        workflow_run_id=workflow_run_id,
                        signal=signal,
                        review_status="NO_TRADE",
                        reasons=signal.review_reasons,
                    )
                )
                continue

            risk_state = self.risk_engine.evaluate(
                signal=signal,
                workflow_run_id=workflow_run_id,
                run_date=run_date,
                data_quality_status=data_quality_status,
            )
            review_reasons = _normalized_review_reasons(signal, risk_state.reason_code, risk_state.reason)
            review_status = "ACCEPTED" if risk_state.approved else "REJECTED"
            self.repository.store_signal_review(
                _build_signal_review(
                    workflow_run_id=workflow_run_id,
                    signal=signal,
                    review_status=review_status,
                    reasons=review_reasons,
                )
            )
            result = self.execution_simulator.simulate_order(
                workflow_run_id=workflow_run_id,
                signal=signal,
                risk_state=risk_state,
            )
            if result.status == "OPENED":
                orders_opened += 1

        signal_reviews = self.repository.fetch_signal_review_rows_for_run(workflow_run_id)
        signals_evaluated = len(signal_reviews)
        signals_accepted = sum(1 for row in signal_reviews if row.get("review_status") == "ACCEPTED")
        signals_rejected = sum(1 for row in signal_reviews if row.get("review_status") == "REJECTED")
        no_trade_count = sum(1 for row in signal_reviews if row.get("review_status") == "NO_TRADE")

        equity_curve_id = self.execution_simulator.store_equity_curve_snapshot()
        logger.info(
            "Paper trading run finished: %s signals, %s opened simulated orders.",
            signals_evaluated,
            orders_opened,
        )
        summary = PaperRunSummary(
            enabled=True,
            status="COMPLETED",
            workflow_run_id=workflow_run_id,
            active_profile=self.signal_config.profile,
            signals_evaluated=signals_evaluated,
            signals_accepted=signals_accepted,
            signals_rejected=signals_rejected,
            no_trade_count=no_trade_count,
            orders_opened=orders_opened,
            positions_updated=len(position_results),
            equity_curve_id=equity_curve_id,
            notes=notes,
        )
        run_summary_id = self.repository.store_run_summary(summary)
        return PaperRunSummary(
            enabled=summary.enabled,
            status=summary.status,
            workflow_run_id=summary.workflow_run_id,
            active_profile=summary.active_profile,
            signals_evaluated=summary.signals_evaluated,
            signals_accepted=summary.signals_accepted,
            signals_rejected=summary.signals_rejected,
            no_trade_count=summary.no_trade_count,
            orders_opened=summary.orders_opened,
            positions_updated=summary.positions_updated,
            equity_curve_id=summary.equity_curve_id,
            notes=summary.notes,
            run_summary_id=run_summary_id,
        )


def build_paper_trading_orchestrator(
    config: PaperTradingConfig,
    signal_config: PaperSignalConfig,
    repository: PaperTradingRepository,
) -> PaperTradingOrchestrator:
    signal_builder = PaperSignalBuilder(
        signal_config=signal_config,
        default_risk_pct=config.max_risk_per_trade_pct,
    )
    risk_engine = PaperRiskEngine(config=config, repository=repository)
    execution_simulator = PaperExecutionSimulator(config=config, repository=repository)
    return PaperTradingOrchestrator(
        config=config,
        signal_config=signal_config,
        repository=repository,
        signal_builder=signal_builder,
        risk_engine=risk_engine,
        execution_simulator=execution_simulator,
    )


def _build_signal_review(
    workflow_run_id: int,
    signal: PaperSignal,
    review_status: str,
    reasons: list[dict[str, object]],
) -> PaperSignalReview:
    return PaperSignalReview(
        workflow_run_id=workflow_run_id,
        asset=signal.asset,
        signal_action=signal.direction if signal.is_trade_candidate else "NO_TRADE",
        review_status=review_status,
        bias=signal.bias,
        total_score=signal.score,
        confidence=signal.confidence,
        data_completeness=signal.data_completeness,
        active_profile=signal.active_profile,
        reasons=[dict(reason) for reason in reasons],
        warnings=list(signal.warnings),
        signal_source=signal.signal_source,
    )


def _normalized_review_reasons(
    signal: PaperSignal,
    reason_code: str,
    reason_message: str,
) -> list[dict[str, object]]:
    if reason_code == "SIGNAL_ACCEPTED":
        return [
            {
                "code": "SIGNAL_ACCEPTED",
                "message": "Signal met paper-only score, confidence, completeness, and risk rules.",
            }
        ]

    reasons: list[dict[str, object]] = []
    if reason_code == "DATA_QUALITY_NOT_ACCEPTABLE":
        reasons.append(
            {
                "code": "DATA_QUALITY_NOT_ACCEPTABLE",
                "message": reason_message,
            }
        )
    reasons.append(
        {
            "code": "RISK_REJECTED",
            "message": reason_message,
        }
    )
    return reasons
