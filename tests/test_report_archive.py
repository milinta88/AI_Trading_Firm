from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from analytics.report_archive import ArchiveQuery, ReportArchive
from database.init_db import initialize_database


def test_report_archive_loads_latest_reports_and_messages(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    _insert_report(database_path, 1, "2026-05-28", "COMPLETED", "BTC brief")
    _insert_report(database_path, 2, "2026-05-29", "COMPLETED", "Gold macro brief")
    _insert_message(database_path, 2, "DRY_RUN", "Telegram preview for Gold macro brief")

    archive = ReportArchive(database_path).load(ArchiveQuery(limit=10))

    assert archive.database_available is True
    assert archive.latest_report is not None
    assert archive.latest_report.workflow_run_id == 2
    assert len(archive.recent_reports) == 2
    assert archive.recent_messages[0].status == "DRY_RUN"


def test_report_archive_filters_keyword_status_and_date(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    _insert_report(database_path, 1, "2026-05-27", "FAILED", "Old failed report")
    _insert_report(database_path, 2, "2026-05-29", "COMPLETED", "BTC funding rate review")
    _insert_message(database_path, 2, "DRY_RUN", "Telegram BTC funding preview")

    archive = ReportArchive(database_path).load(
        ArchiveQuery(
            start_date=date(2026, 5, 28),
            end_date=date(2026, 5, 30),
            keyword="funding",
            status="COMPLETED",
            limit=10,
        )
    )

    assert [item.workflow_run_id for item in archive.recent_reports] == [2]
    assert archive.recent_messages == []


def _insert_report(database_path: Path, run_id: int, run_date: str, status: str, report_text: str) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (
                id, run_date, mode, status, summary, report_text, completed_at
            )
            VALUES (?, ?, 'research', ?, ?, ?, ?)
            """,
            (run_id, run_date, status, f"summary {run_id}", report_text, f"{run_date} 12:00:00"),
        )
        connection.commit()


def _insert_message(database_path: Path, workflow_run_id: int, status: str, message_preview: str) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO outbound_messages (
                workflow_run_id, channel, status, recipient, message_preview, created_at
            )
            VALUES (?, 'telegram', ?, 'not-configured', ?, '2026-05-29 12:10:00')
            """,
            (workflow_run_id, status, message_preview),
        )
        connection.commit()
