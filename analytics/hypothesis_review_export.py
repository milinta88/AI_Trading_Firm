from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any


STRATEGY_HYPOTHESIS_HEADERS = [
    "id",
    "workflow_run_id",
    "asset",
    "hypothesis_name",
    "direction_bias",
    "regime",
    "readiness_score",
    "score",
    "confidence",
    "data_completeness",
    "hypothesis_status",
    "suggested_strategy_family",
    "suggested_holding_period",
    "reasons_json",
    "blockers_json",
    "warnings_json",
    "invalidation_notes",
    "created_at",
]

HYPOTHESIS_OUTCOME_HEADERS = [
    "id",
    "hypothesis_id",
    "workflow_run_id",
    "asset",
    "hypothesis_name",
    "direction_bias",
    "strategy_family",
    "horizon_hours",
    "created_at",
    "evaluated_at",
    "entry_reference_price",
    "followup_price",
    "move_pct",
    "max_favorable_move_pct",
    "max_adverse_move_pct",
    "outcome_status",
    "reason",
    "warnings_json",
]

HYPOTHESIS_REVIEW_SUMMARY_HEADERS = [
    "id",
    "created_at",
    "lookback_days",
    "total_outcomes",
    "evaluated_outcomes",
    "favorable_count",
    "unfavorable_count",
    "neutral_count",
    "insufficient_followup_count",
    "blocked_not_evaluated_count",
    "favorable_rate",
    "unfavorable_rate",
    "neutral_rate",
    "by_asset_json",
    "by_strategy_family_json",
    "by_regime_json",
    "by_horizon_json",
    "by_readiness_bucket_json",
    "by_hypothesis_status_json",
    "avg_move_pct",
    "avg_max_favorable_move_pct",
    "avg_max_adverse_move_pct",
    "promoted_candidates_json",
    "blocked_candidates_json",
    "candidate_progress_json",
    "warnings_json",
]

HYPOTHESIS_REVIEW_NOTE_HEADERS = [
    "id",
    "created_at",
    "updated_at",
    "note_type",
    "reference_type",
    "reference_id",
    "asset",
    "strategy_family",
    "regime",
    "horizon_hours",
    "title",
    "note_text",
    "tags",
    "is_deleted",
]


@dataclass(frozen=True)
class HypothesisReviewExportArtifact:
    export_name: str
    path: Path


class HypothesisReviewExportService:
    """Read-only CSV export helper for persisted hypothesis review data."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def export_strategy_hypotheses_csv(self) -> str:
        rows = self._fetch_rows(
            query="SELECT * FROM strategy_hypotheses ORDER BY id DESC",
            table_name="strategy_hypotheses",
        )
        return rows_to_csv(rows, STRATEGY_HYPOTHESIS_HEADERS)

    def export_hypothesis_outcomes_csv(self) -> str:
        rows = self._fetch_rows(
            query="SELECT * FROM strategy_hypothesis_outcomes ORDER BY id DESC",
            table_name="strategy_hypothesis_outcomes",
        )
        return rows_to_csv(rows, HYPOTHESIS_OUTCOME_HEADERS)

    def export_review_summaries_csv(self) -> str:
        rows = self._fetch_rows(
            query="SELECT * FROM hypothesis_review_summaries ORDER BY id DESC",
            table_name="hypothesis_review_summaries",
        )
        return rows_to_csv(rows, HYPOTHESIS_REVIEW_SUMMARY_HEADERS)

    def export_review_notes_csv(self) -> str:
        rows = self._fetch_rows(
            query="SELECT * FROM hypothesis_review_notes WHERE is_deleted = 0 ORDER BY id DESC",
            table_name="hypothesis_review_notes",
        )
        return rows_to_csv(rows, HYPOTHESIS_REVIEW_NOTE_HEADERS)

    def write_review_exports(
        self,
        export_dir: Path,
        timestamp: datetime | None = None,
    ) -> list[HypothesisReviewExportArtifact]:
        resolved_timestamp = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
        export_dir.mkdir(parents=True, exist_ok=True)

        artifacts = [
            HypothesisReviewExportArtifact(
                export_name="strategy_hypotheses",
                path=export_dir / f"strategy_hypotheses_{resolved_timestamp}.csv",
            ),
            HypothesisReviewExportArtifact(
                export_name="strategy_hypothesis_outcomes",
                path=export_dir / f"strategy_hypothesis_outcomes_{resolved_timestamp}.csv",
            ),
            HypothesisReviewExportArtifact(
                export_name="hypothesis_review_summaries",
                path=export_dir / f"hypothesis_review_summaries_{resolved_timestamp}.csv",
            ),
        ]
        payloads = {
            "strategy_hypotheses": self.export_strategy_hypotheses_csv(),
            "strategy_hypothesis_outcomes": self.export_hypothesis_outcomes_csv(),
            "hypothesis_review_summaries": self.export_review_summaries_csv(),
        }
        for artifact in artifacts:
            artifact.path.write_text(payloads[artifact.export_name], encoding="utf-8", newline="")
        return artifacts

    def _fetch_rows(self, query: str, table_name: str) -> list[dict[str, Any]]:
        if not self.database_path.exists():
            return []
        try:
            with closing(self._connect_read_only()) as connection:
                if not _table_exists(connection, table_name):
                    return []
                return [dict(row) for row in connection.execute(query).fetchall()]
        except sqlite3.Error:
            return []

    def _connect_read_only(self) -> sqlite3.Connection:
        uri = f"{self.database_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection


def rows_to_csv(rows: list[dict[str, Any]], headers: list[str]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({header: _csv_cell(row.get(header)) for header in headers})
    return output.getvalue()


def _csv_cell(value: Any) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, (str, int, float)):
        return value
    return str(value)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None
