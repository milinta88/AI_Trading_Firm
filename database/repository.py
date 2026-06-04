from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from core.models import (
    AnalysisResult,
    HypothesisOutcome,
    HypothesisReviewSummary,
    MarketDataPoint,
    ResearchReadinessResult,
    RiskStatus,
    StrategyHypothesis,
)

logger = logging.getLogger(__name__)
_UNSET = object()


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

    def store_strategy_hypothesis(
        self,
        workflow_run_id: int,
        hypothesis: StrategyHypothesis,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO strategy_hypotheses (
                    workflow_run_id,
                    asset,
                    hypothesis_name,
                    direction_bias,
                    regime,
                    readiness_score,
                    score,
                    confidence,
                    data_completeness,
                    hypothesis_status,
                    suggested_strategy_family,
                    suggested_holding_period,
                    reasons_json,
                    blockers_json,
                    warnings_json,
                    invalidation_notes,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_run_id,
                    hypothesis.asset,
                    hypothesis.hypothesis_name,
                    hypothesis.direction_bias,
                    hypothesis.regime,
                    hypothesis.readiness_score,
                    hypothesis.score,
                    hypothesis.confidence,
                    hypothesis.data_completeness,
                    hypothesis.hypothesis_status,
                    hypothesis.suggested_strategy_family,
                    hypothesis.suggested_holding_period,
                    json.dumps(hypothesis.reasons),
                    json.dumps(hypothesis.blockers),
                    json.dumps(hypothesis.warnings),
                    hypothesis.invalidation_notes,
                    hypothesis.created_at.isoformat(),
                ),
            )
        logger.info(
            "Stored strategy hypothesis for %s in workflow run %s.",
            hypothesis.asset,
            workflow_run_id,
        )

    def store_strategy_hypothesis_outcome(self, outcome: HypothesisOutcome) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO strategy_hypothesis_outcomes (
                    hypothesis_id,
                    workflow_run_id,
                    asset,
                    hypothesis_name,
                    direction_bias,
                    strategy_family,
                    horizon_hours,
                    created_at,
                    evaluated_at,
                    entry_reference_price,
                    followup_price,
                    move_pct,
                    max_favorable_move_pct,
                    max_adverse_move_pct,
                    outcome_status,
                    reason,
                    warnings_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(hypothesis_id, horizon_hours) DO UPDATE SET
                    workflow_run_id = excluded.workflow_run_id,
                    asset = excluded.asset,
                    hypothesis_name = excluded.hypothesis_name,
                    direction_bias = excluded.direction_bias,
                    strategy_family = excluded.strategy_family,
                    created_at = excluded.created_at,
                    evaluated_at = excluded.evaluated_at,
                    entry_reference_price = excluded.entry_reference_price,
                    followup_price = excluded.followup_price,
                    move_pct = excluded.move_pct,
                    max_favorable_move_pct = excluded.max_favorable_move_pct,
                    max_adverse_move_pct = excluded.max_adverse_move_pct,
                    outcome_status = excluded.outcome_status,
                    reason = excluded.reason,
                    warnings_json = excluded.warnings_json
                """,
                (
                    outcome.hypothesis_id,
                    outcome.workflow_run_id,
                    outcome.asset,
                    outcome.hypothesis_name,
                    outcome.direction_bias,
                    outcome.strategy_family,
                    outcome.horizon_hours,
                    outcome.created_at.isoformat(),
                    outcome.evaluated_at.isoformat(),
                    outcome.entry_reference_price,
                    outcome.followup_price,
                    outcome.move_pct,
                    outcome.max_favorable_move_pct,
                    outcome.max_adverse_move_pct,
                    outcome.outcome_status,
                    outcome.reason,
                    json.dumps(outcome.warnings),
                ),
            )
        logger.info(
            "Stored strategy hypothesis outcome for %s horizon %sh.",
            outcome.asset,
            outcome.horizon_hours,
        )

    def store_hypothesis_review_summary(self, summary: HypothesisReviewSummary) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO hypothesis_review_summaries (
                    created_at,
                    lookback_days,
                    total_outcomes,
                    evaluated_outcomes,
                    favorable_count,
                    unfavorable_count,
                    neutral_count,
                    insufficient_followup_count,
                    blocked_not_evaluated_count,
                    favorable_rate,
                    unfavorable_rate,
                    neutral_rate,
                    by_asset_json,
                    by_strategy_family_json,
                    by_regime_json,
                    by_horizon_json,
                    by_readiness_bucket_json,
                    by_hypothesis_status_json,
                    avg_move_pct,
                    avg_max_favorable_move_pct,
                    avg_max_adverse_move_pct,
                    promoted_candidates_json,
                    blocked_candidates_json,
                    candidate_progress_json,
                    warnings_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (summary.created_at or datetime.now(UTC)).isoformat(),
                    int(summary.lookback_days or 0),
                    summary.total_outcomes,
                    summary.evaluated_outcomes,
                    summary.favorable_count,
                    summary.unfavorable_count,
                    summary.neutral_count,
                    summary.insufficient_followup_count,
                    summary.blocked_not_evaluated_count,
                    summary.favorable_rate,
                    summary.unfavorable_rate,
                    summary.neutral_rate,
                    json.dumps(summary.by_asset),
                    json.dumps(summary.by_strategy_family),
                    json.dumps(summary.by_regime),
                    json.dumps(summary.by_horizon),
                    json.dumps(summary.by_readiness_bucket),
                    json.dumps(summary.by_hypothesis_status),
                    summary.avg_move_pct,
                    summary.avg_max_favorable_move_pct,
                    summary.avg_max_adverse_move_pct,
                    json.dumps(summary.promoted_candidates),
                    json.dumps(summary.blocked_candidates),
                    json.dumps(summary.candidate_progress),
                    json.dumps(summary.warnings),
                ),
            )
        logger.info(
            "Stored hypothesis review summary for %s evaluated outcomes.",
            summary.evaluated_outcomes,
        )

    def add_hypothesis_review_note(
        self,
        *,
        note_type: str,
        reference_type: str,
        note_text: str,
        reference_id: str | None = None,
        asset: str | None = None,
        strategy_family: str | None = None,
        regime: str | None = None,
        horizon_hours: int | None = None,
        title: str | None = None,
        tags: str | None = None,
    ) -> int:
        with self._connect() as connection:
            if not self._table_exists(connection, "hypothesis_review_notes"):
                return 0
            cursor = connection.execute(
                """
                INSERT INTO hypothesis_review_notes (
                    note_type,
                    reference_type,
                    reference_id,
                    asset,
                    strategy_family,
                    regime,
                    horizon_hours,
                    title,
                    note_text,
                    tags
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note_type,
                    reference_type,
                    reference_id,
                    asset,
                    strategy_family,
                    regime,
                    horizon_hours,
                    title,
                    note_text,
                    tags,
                ),
            )
            return int(cursor.lastrowid)

    def list_hypothesis_review_notes(
        self,
        *,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> list[dict[str, object]]:
        with self._connect() as connection:
            if not self._table_exists(connection, "hypothesis_review_notes"):
                return []
            predicate = "" if include_deleted else "WHERE is_deleted = 0"
            rows = connection.execute(
                f"""
                SELECT * FROM hypothesis_review_notes
                {predicate}
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_hypothesis_review_note(
        self,
        note_id: int,
        *,
        note_type: object = _UNSET,
        reference_type: object = _UNSET,
        reference_id: object = _UNSET,
        asset: object = _UNSET,
        strategy_family: object = _UNSET,
        regime: object = _UNSET,
        horizon_hours: object = _UNSET,
        title: object = _UNSET,
        note_text: object = _UNSET,
        tags: object = _UNSET,
    ) -> bool:
        with self._connect() as connection:
            if not self._table_exists(connection, "hypothesis_review_notes"):
                return False

            assignments: list[str] = []
            values: list[object] = []
            for column_name, value in (
                ("note_type", note_type),
                ("reference_type", reference_type),
                ("reference_id", reference_id),
                ("asset", asset),
                ("strategy_family", strategy_family),
                ("regime", regime),
                ("horizon_hours", horizon_hours),
                ("title", title),
                ("note_text", note_text),
                ("tags", tags),
            ):
                if value is _UNSET:
                    continue
                assignments.append(f"{column_name} = ?")
                values.append(value)

            if not assignments:
                return False

            assignments.append("updated_at = ?")
            values.append(datetime.now(UTC).isoformat())
            values.append(note_id)
            cursor = connection.execute(
                f"""
                UPDATE hypothesis_review_notes
                SET {", ".join(assignments)}
                WHERE id = ?
                """,
                tuple(values),
            )
            return cursor.rowcount > 0

    def soft_delete_hypothesis_review_note(self, note_id: int) -> bool:
        with self._connect() as connection:
            if not self._table_exists(connection, "hypothesis_review_notes"):
                return False
            cursor = connection.execute(
                """
                UPDATE hypothesis_review_notes
                SET is_deleted = 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (datetime.now(UTC).isoformat(), note_id),
            )
            return cursor.rowcount > 0

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None
