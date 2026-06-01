from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from core.models import AnalysisResult, MarketDataPoint, ResearchReadinessResult, RiskStatus

logger = logging.getLogger(__name__)


class WorkflowRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def create_workflow_run(self, run_date: date, mode: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO workflow_runs (run_date, mode, status)
                VALUES (?, ?, ?)
                """,
                (run_date.isoformat(), mode, "RUNNING"),
            )
            workflow_run_id = int(cursor.lastrowid)
            logger.info("Created workflow run %s.", workflow_run_id)
            return workflow_run_id

    def complete_workflow_run(
        self,
        workflow_run_id: int,
        status: str,
        summary: str,
        report_text: str,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE workflow_runs
                SET status = ?,
                    summary = ?,
                    report_text = ?,
                    error_message = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, summary, report_text, error_message, workflow_run_id),
            )
        logger.info("Workflow run %s marked as %s.", workflow_run_id, status)

    def store_analysis_result(self, workflow_run_id: int, bot_name: str, result: AnalysisResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO bot_assessments (workflow_run_id, bot_name, asset, score, bias, reasons_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_run_id,
                    bot_name,
                    result.asset,
                    result.score,
                    result.bias,
                    json.dumps(result.reasons),
                ),
            )
        logger.info("Stored %s assessment for workflow run %s.", bot_name, workflow_run_id)

    def store_risk_status(self, workflow_run_id: int, risk_status: RiskStatus) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO risk_snapshots (
                    workflow_run_id,
                    status,
                    trade_permission,
                    data_quality,
                    daily_loss_pct,
                    weekly_loss_pct,
                    notes_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_run_id,
                    risk_status.status,
                    risk_status.trade_permission,
                    risk_status.data_quality,
                    risk_status.daily_loss_pct,
                    risk_status.weekly_loss_pct,
                    json.dumps(risk_status.notes),
                ),
            )
        logger.info("Stored risk snapshot for workflow run %s.", workflow_run_id)

    def store_outbound_message(
        self,
        workflow_run_id: int,
        channel: str,
        status: str,
        recipient: str,
        message: str,
        error_message: str | None = None,
    ) -> None:
        preview = message[:500]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outbound_messages (
                    workflow_run_id,
                    channel,
                    status,
                    recipient,
                    message_preview,
                    error_message
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (workflow_run_id, channel, status, recipient, preview, error_message),
            )
        logger.info("Stored outbound %s message for workflow run %s.", channel, workflow_run_id)

    def store_market_snapshot(self, workflow_run_id: int, snapshot: MarketDataPoint) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO market_snapshots (
                    workflow_run_id,
                    timestamp,
                    asset,
                    source,
                    data_type,
                    value_json,
                    status,
                    error_summary
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_run_id,
                    snapshot.timestamp.isoformat(),
                    snapshot.asset,
                    snapshot.source,
                    snapshot.data_type,
                    json.dumps(snapshot.value) if snapshot.value is not None else None,
                    snapshot.status,
                    snapshot.error_summary,
                ),
            )
        logger.info("Stored market snapshot %s for workflow run %s.", snapshot.key, workflow_run_id)

    def store_score_snapshot(self, workflow_run_id: int, result: AnalysisResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO score_snapshots (
                    workflow_run_id,
                    timestamp,
                    asset,
                    total_score,
                    bias,
                    confidence,
                    data_completeness,
                    components_json,
                    reasons_json,
                    warnings_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_run_id,
                    datetime.now(UTC).isoformat(),
                    result.asset,
                    result.total_score,
                    result.bias,
                    result.confidence,
                    result.data_completeness,
                    json.dumps([asdict(component) for component in result.components]),
                    json.dumps(result.reasons),
                    json.dumps(result.warnings),
                ),
            )
        logger.info("Stored score snapshot for %s in workflow run %s.", result.asset, workflow_run_id)

    def store_research_readiness_snapshot(
        self,
        workflow_run_id: int,
        result: ResearchReadinessResult,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_readiness_snapshots (
                    workflow_run_id,
                    asset,
                    readiness_score,
                    regime,
                    data_completeness,
                    decision_ready,
                    stale_sources_json,
                    missing_sources_json,
                    warnings_json,
                    no_trade_reasons_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_run_id,
                    result.asset,
                    result.readiness_score,
                    result.regime,
                    result.data_completeness,
                    int(result.decision_ready),
                    json.dumps(result.stale_sources),
                    json.dumps(result.missing_sources),
                    json.dumps(result.warnings),
                    json.dumps(result.no_trade_reasons),
                ),
            )
        logger.info("Stored research readiness snapshot for %s in workflow run %s.", result.asset, workflow_run_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection
