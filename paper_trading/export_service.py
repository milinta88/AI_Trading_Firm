from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

from paper_trading.analytics import PaperAnalytics


SIGNAL_REVIEW_HEADERS = [
    "id",
    "created_at",
    "workflow_run_id",
    "asset",
    "signal_action",
    "review_status",
    "bias",
    "total_score",
    "confidence",
    "data_completeness",
    "active_profile",
    "signal_source",
    "reasons_json",
    "warnings_json",
]

RUN_SUMMARY_HEADERS = [
    "id",
    "run_timestamp",
    "workflow_run_id",
    "status",
    "active_profile",
    "signals_evaluated",
    "signals_accepted",
    "signals_rejected",
    "no_trade_count",
    "orders_opened",
    "positions_updated",
    "equity_snapshot_id",
    "notes_json",
]

CLOSED_POSITION_HEADERS = [
    "id",
    "order_id",
    "workflow_run_id",
    "opened_at",
    "closed_at",
    "asset",
    "direction",
    "entry_price",
    "exit_price",
    "stop_loss",
    "take_profit",
    "size",
    "status",
    "pnl_abs",
    "pnl_pct",
    "reason_json",
]

PERFORMANCE_SUMMARY_HEADERS = [
    "starting_equity",
    "latest_equity",
    "total_pnl_abs",
    "total_pnl_pct",
    "max_drawdown_pct",
    "total_orders",
    "open_positions",
    "closed_positions",
    "total_trades",
    "winning_trades",
    "losing_trades",
    "win_rate",
    "gross_profit",
    "gross_loss",
    "profit_factor",
    "average_pnl",
    "average_r_multiple",
]


@dataclass(frozen=True)
class PaperExportArtifact:
    export_name: str
    path: Path


class PaperTradingExportService:
    """Read-only CSV export helper for local simulated paper-trading review data."""

    def __init__(self, database_path: Path, starting_equity: float) -> None:
        self.database_path = database_path
        self.starting_equity = starting_equity

    def export_signal_reviews_csv(self) -> str:
        rows = self._fetch_rows(
            query="SELECT * FROM paper_signal_reviews ORDER BY id DESC",
            table_name="paper_signal_reviews",
        )
        return _rows_to_csv(rows, SIGNAL_REVIEW_HEADERS)

    def export_run_summaries_csv(self) -> str:
        rows = self._fetch_rows(
            query="SELECT * FROM paper_run_summaries ORDER BY id DESC",
            table_name="paper_run_summaries",
        )
        return _rows_to_csv(rows, RUN_SUMMARY_HEADERS)

    def export_closed_positions_csv(self) -> str:
        rows = self._fetch_rows(
            query="SELECT * FROM paper_positions WHERE status != 'OPEN' ORDER BY id DESC",
            table_name="paper_positions",
        )
        return _rows_to_csv(rows, CLOSED_POSITION_HEADERS)

    def export_performance_summary_csv(self) -> str:
        report = PaperAnalytics(
            database_path=self.database_path,
            starting_equity=self.starting_equity,
        ).build_report(limit=1)
        performance_row = asdict(report.performance)
        return _rows_to_csv([performance_row], PERFORMANCE_SUMMARY_HEADERS)

    def write_review_exports(
        self,
        export_dir: Path,
        timestamp: datetime | None = None,
    ) -> list[PaperExportArtifact]:
        resolved_timestamp = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
        export_dir.mkdir(parents=True, exist_ok=True)

        artifacts = [
            PaperExportArtifact(
                export_name="paper_signal_reviews",
                path=export_dir / f"paper_signal_reviews_{resolved_timestamp}.csv",
            ),
            PaperExportArtifact(
                export_name="paper_run_summaries",
                path=export_dir / f"paper_run_summaries_{resolved_timestamp}.csv",
            ),
        ]
        payloads = {
            "paper_signal_reviews": self.export_signal_reviews_csv(),
            "paper_run_summaries": self.export_run_summaries_csv(),
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


def _rows_to_csv(rows: list[dict[str, Any]], headers: list[str]) -> str:
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
