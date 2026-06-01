from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loads_trend_context(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)
    _insert_market_snapshot(database_path, "BTC", "price", {"price": 100.0})
    _insert_market_snapshot(database_path, "BTC", "price", {"price": 110.0})

    data = load_dashboard_data(tmp_path)
    trend_by_key = {row["key"]: row for row in data.trend_results}

    assert trend_by_key["btc_price"]["status"] == "OK"
    assert trend_by_key["btc_price"]["direction"] == "rising"


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


def _insert_market_snapshot(database_path: Path, asset: str, data_type: str, value: dict[str, float]) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (run_date, mode, status)
            VALUES ('2026-05-29', 'research', 'COMPLETED')
            """
        )
        workflow_run_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            """
            INSERT INTO market_snapshots (
                workflow_run_id, timestamp, asset, source, data_type, value_json, status, error_summary
            )
            VALUES (?, '2026-05-29T00:00:00+00:00', ?, 'test', ?, ?, 'OK', NULL)
            """,
            (workflow_run_id, asset, data_type, json.dumps(value)),
        )
        connection.commit()
