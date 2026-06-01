from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loader_includes_report_archive(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status, summary, report_text, completed_at)
            VALUES (1, '2026-05-29', 'research', 'COMPLETED', 'summary', 'Daily brief archive text', '2026-05-29 12:00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO outbound_messages (workflow_run_id, channel, status, recipient, message_preview, created_at)
            VALUES (1, 'telegram', 'DRY_RUN', 'not-configured', 'message archive preview', '2026-05-29 12:01:00')
            """
        )
        connection.commit()

    data = load_dashboard_data(tmp_path)

    assert data.archive_latest_report is not None
    assert data.archive_latest_report["text"] == "Daily brief archive text"
    assert data.archive_recent_messages[0]["status"] == "DRY_RUN"
    assert len(data.archive_items) == 2


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "\n".join(
            [
                "app:",
                "  name: AI Trading Firm",
                "  mode: research",
                "database:",
                "  path: data/database.db",
                "risk:",
                "  execution_enabled: false",
            ]
        ),
        encoding="utf-8",
    )
