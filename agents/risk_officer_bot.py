from __future__ import annotations

import logging

from core.models import AnalysisResult, DataQualityReport, RiskStatus

logger = logging.getLogger(__name__)


class RiskOfficerBot:
    """Applies Phase 1 safety rules for the research-only workflow."""

    name = "risk_officer_bot"

    def __init__(self, max_daily_loss_pct: float, max_weekly_loss_pct: float, execution_enabled: bool) -> None:
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_weekly_loss_pct = max_weekly_loss_pct
        self.execution_enabled = execution_enabled

    def evaluate(
        self,
        gold_result: AnalysisResult,
        btc_result: AnalysisResult,
        data_quality_report: DataQualityReport | None = None,
    ) -> RiskStatus:
        average_score = (gold_result.score + btc_result.score) / 2
        minimum_score = min(gold_result.score, btc_result.score)
        data_quality_status = data_quality_report.overall_status if data_quality_report else "PASS"
        low_confidence_assets = [result.asset for result in (gold_result, btc_result) if result.confidence == "Low"]
        low_completeness_assets = [
            result.asset for result in (gold_result, btc_result) if result.data_completeness < 40
        ]

        notes = [
            "Phase 1 remains research-only; no real orders can be sent.",
            f"Configured daily loss cap: {self.max_daily_loss_pct:.2f}%.",
            f"Configured weekly loss cap: {self.max_weekly_loss_pct:.2f}%.",
        ]

        if data_quality_status == "FAIL":
            status = "ELEVATED"
            notes.append("Critical read-only market data is unavailable or stale, so the system remains WATCH ONLY.")
        elif minimum_score < 50:
            status = "ELEVATED"
            notes.append("At least one asset has weak placeholder conviction below the research threshold.")
        elif data_quality_status == "WARNING":
            status = "CAUTION"
            notes.append("Some read-only data sources are unavailable or not configured yet.")
        elif average_score >= 65:
            status = "NORMAL"
            notes.append("Signals are constructive, but execution remains disabled by design.")
        else:
            status = "CAUTION"
            notes.append("Signals are mixed, so observation mode is appropriate.")

        if low_confidence_assets:
            notes.append(f"Low confidence detected for: {', '.join(low_confidence_assets)}.")
            status = self._escalate_status(status, "CAUTION")

        if low_completeness_assets:
            notes.append(f"Low data completeness detected for: {', '.join(low_completeness_assets)}.")
            status = self._escalate_status(status, "CAUTION")

        trade_permission = "WATCH ONLY"
        if self.execution_enabled:
            notes.append("Execution flag is enabled in config, but the MVP does not implement order routing.")

        result = RiskStatus(
            status=status,
            trade_permission=trade_permission,
            data_quality=data_quality_status,
            daily_loss_pct=0.0,
            weekly_loss_pct=0.0,
            notes=notes,
        )
        logger.info("Risk officer bot completed with %s status.", result.status)
        return result

    @staticmethod
    def _escalate_status(current_status: str, target_status: str) -> str:
        severity = {
            "NORMAL": 0,
            "CAUTION": 1,
            "ELEVATED": 2,
        }
        return target_status if severity[target_status] > severity[current_status] else current_status
