from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from dashboard.data_loader import load_dashboard_data, parse_json_value
from database.init_db import initialize_database


def test_dashboard_loader_handles_missing_database(tmp_path: Path) -> None:
    _write_config(tmp_path, database_path="data/missing.db")

    data = load_dashboard_data(tmp_path)

    assert data.database_available is False
    assert "Database not found" in data.database_message
    assert data.execution_enabled is False


def test_dashboard_loader_reads_latest_snapshots(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status, summary, report_text)
            VALUES (1, '2026-05-28', 'research', 'COMPLETED', 'summary', 'daily brief text')
            """
        )
        connection.execute(
            """
            INSERT INTO market_snapshots (
                workflow_run_id, timestamp, asset, source, data_type, value_json, status, error_summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "2026-05-28T00:00:00+00:00",
                "BTC",
                "Binance USD-M Futures API",
                "funding_rate",
                json.dumps({"funding_rate": 0.00038246}),
                "OK",
                None,
            ),
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "2026-05-28T00:00:00+00:00",
                "BTC",
                62,
                "Bullish",
                "Medium",
                100,
                json.dumps([{"name": "Funding Rate", "status": "OK"}]),
                json.dumps(["Reason"]),
                json.dumps(["Warning"]),
            ),
        )
        connection.execute(
            """
            INSERT INTO risk_snapshots (
                workflow_run_id, status, trade_permission, data_quality, daily_loss_pct, weekly_loss_pct, notes_json
            )
            VALUES (1, 'CAUTION', 'WATCH ONLY', 'WARNING', 0.0, 0.0, ?)
            """,
            (json.dumps(["Execution disabled"]),),
        )
        connection.execute(
            """
            INSERT INTO outbound_messages (workflow_run_id, channel, status, recipient, message_preview)
            VALUES (1, 'telegram', 'DRY_RUN', 'not-configured', 'preview')
            """
        )
        connection.commit()

    data = load_dashboard_data(tmp_path)

    assert data.database_available is True
    assert data.latest_workflow_run is not None
    assert data.latest_report_text == "daily brief text"
    assert data.latest_market_snapshots[0]["display_value"] == "0.0382%"
    assert data.latest_score_snapshots[0]["confidence"] == "Medium"
    assert data.latest_risk_snapshot is not None
    assert data.recent_messages[0]["status"] == "DRY_RUN"


def test_parse_json_value_falls_back_on_invalid_json() -> None:
    assert parse_json_value("{bad", fallback=[]) == []


def _write_config(tmp_path: Path, database_path: str = "data/database.db") -> None:
    (tmp_path / "config.yaml").write_text(
        "\n".join(
            [
                "app:",
                "  name: AI Trading Firm",
                "  mode: research",
                "database:",
                f"  path: {database_path}",
                "risk:",
                "  execution_enabled: false",
            ]
        ),
        encoding="utf-8",
    )
