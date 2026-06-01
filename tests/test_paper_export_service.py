from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from database.init_db import initialize_database
from paper_trading.export_service import (
    CLOSED_POSITION_HEADERS,
    PERFORMANCE_SUMMARY_HEADERS,
    RUN_SUMMARY_HEADERS,
    SIGNAL_REVIEW_HEADERS,
    PaperTradingExportService,
)


def test_export_service_returns_headers_when_database_is_missing(tmp_path: Path) -> None:
    service = PaperTradingExportService(tmp_path / "missing.db", starting_equity=10_000.0)

    assert service.export_signal_reviews_csv().splitlines()[0] == ",".join(SIGNAL_REVIEW_HEADERS)
    assert service.export_run_summaries_csv().splitlines()[0] == ",".join(RUN_SUMMARY_HEADERS)
    assert service.export_closed_positions_csv().splitlines()[0] == ",".join(CLOSED_POSITION_HEADERS)
    assert service.export_performance_summary_csv().splitlines()[0] == ",".join(PERFORMANCE_SUMMARY_HEADERS)


def test_export_service_handles_empty_tables_and_writes_header_only_files(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)
    service = PaperTradingExportService(database_path, starting_equity=10_000.0)

    signal_csv = service.export_signal_reviews_csv()
    run_csv = service.export_run_summaries_csv()
    closed_csv = service.export_closed_positions_csv()
    performance_csv = service.export_performance_summary_csv()

    assert signal_csv.splitlines() == [",".join(SIGNAL_REVIEW_HEADERS)]
    assert run_csv.splitlines() == [",".join(RUN_SUMMARY_HEADERS)]
    assert closed_csv.splitlines() == [",".join(CLOSED_POSITION_HEADERS)]
    assert performance_csv.splitlines()[0] == ",".join(PERFORMANCE_SUMMARY_HEADERS)
    assert "10000.0,10000.0,0.0,0.0" in performance_csv


def test_export_service_writes_review_exports_to_local_export_folder(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)
    _seed_review_tables(database_path)
    service = PaperTradingExportService(database_path, starting_equity=10_000.0)

    artifacts = service.write_review_exports(
        tmp_path / "data" / "exports",
        timestamp=datetime(2026, 6, 1, 8, 30, 45),
    )

    assert [artifact.path.name for artifact in artifacts] == [
        "paper_signal_reviews_20260601_083045.csv",
        "paper_run_summaries_20260601_083045.csv",
    ]
    assert artifacts[0].path.read_text(encoding="utf-8").splitlines()[0] == ",".join(SIGNAL_REVIEW_HEADERS)
    assert artifacts[1].path.read_text(encoding="utf-8").splitlines()[0] == ",".join(RUN_SUMMARY_HEADERS)


def _seed_review_tables(database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-06-01', 'research', 'COMPLETED')
            """
        )
        connection.execute(
            """
            INSERT INTO paper_signal_reviews (
                workflow_run_id, asset, signal_action, review_status, bias, total_score,
                confidence, data_completeness, active_profile, signal_source, reasons_json, warnings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "BTC",
                "LONG",
                "ACCEPTED",
                "Bullish",
                72,
                "Medium",
                95,
                "balanced",
                "paper_signal_balanced",
                json.dumps([{"code": "SIGNAL_ACCEPTED", "message": "Simulated candidate approved."}]),
                json.dumps(["Simulated only."]),
            ),
        )
        connection.execute(
            """
            INSERT INTO paper_run_summaries (
                workflow_run_id, status, active_profile, signals_evaluated, signals_accepted,
                signals_rejected, no_trade_count, orders_opened, positions_updated, equity_snapshot_id, notes_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "COMPLETED",
                "balanced",
                1,
                1,
                0,
                0,
                1,
                0,
                None,
                json.dumps(["Simulated only."]),
            ),
        )

