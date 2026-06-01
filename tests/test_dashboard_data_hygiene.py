from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loader_includes_data_hygiene_report(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-05-29', 'research', 'COMPLETED')
            """
        )
        connection.execute(
            """
            INSERT INTO market_snapshots (
                workflow_run_id, timestamp, asset, source, data_type, value_json, status, error_summary
            )
            VALUES (1, '2026-05-29T00:00:00+00:00', 'BTC', 'test', 'price', ?, 'OK', NULL)
            """,
            (json.dumps({"price": 100.0}),),
        )
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
            VALUES (1, '2026-05-29T00:00:00+00:00', 'BTC', 55, 'Neutral', 'Medium', 75, '[]', '[]', '[]')
            """
        )
        connection.commit()

    data = load_dashboard_data(tmp_path)

    assert data.data_hygiene_summary["total_market_snapshots"] == 1
    assert data.data_hygiene_summary["total_score_snapshots"] == 1
    assert data.data_hygiene_status_distribution[0]["status"] == "OK"
    assert data.data_hygiene_checks


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
