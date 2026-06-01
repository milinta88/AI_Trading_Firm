from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from analytics.data_hygiene import DataHygieneAnalyzer
from database.init_db import initialize_database


def test_data_hygiene_reports_counts_distribution_and_warnings(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    _insert_workflow_run(database_path)
    _insert_market_snapshot(database_path, "BTC", "price", "Binance", "OK", {"price": 100.0})
    _insert_market_snapshot(database_path, "BTC", "price", "Binance", "OK", {"price": 100.0})
    _insert_market_snapshot(database_path, "BTC", "funding_rate", "Binance Futures", "FAIL", None)
    _insert_market_snapshot(database_path, "BTC", "open_interest", "Binance Futures", "OK", None)
    _insert_score_snapshot(database_path, "BTC")

    report = DataHygieneAnalyzer(
        database_path,
        now=datetime(2026, 5, 30, tzinfo=UTC),
        stale_after_hours=72,
    ).analyze()

    checks = {check.check_name: check for check in report.checks}
    assert report.overall_status == "WARNING"
    assert report.summary["total_market_snapshots"] == 4
    assert report.summary["total_score_snapshots"] == 1
    assert checks["Duplicate snapshots"].status == "WARNING"
    assert checks["Null or empty values"].status == "WARNING"
    assert any(row["status"] == "OK" for row in report.status_distribution)


def test_data_hygiene_handles_missing_database(tmp_path: Path) -> None:
    report = DataHygieneAnalyzer(tmp_path / "missing.db").analyze()

    assert report.overall_status == "NOT_AVAILABLE"
    assert report.checks[0].status == "NOT_AVAILABLE"


def _insert_workflow_run(database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-05-29', 'research', 'COMPLETED')
            """
        )
        connection.commit()


def _insert_market_snapshot(
    database_path: Path,
    asset: str,
    data_type: str,
    source: str,
    status: str,
    value: dict[str, float] | None,
) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO market_snapshots (
                workflow_run_id, timestamp, asset, source, data_type, value_json, status, error_summary
            )
            VALUES (1, '2026-05-29T00:00:00+00:00', ?, ?, ?, ?, ?, NULL)
            """,
            (asset, source, data_type, json.dumps(value) if value is not None else None, status),
        )
        connection.commit()


def _insert_score_snapshot(database_path: Path, asset: str) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
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
            VALUES (1, '2026-05-29T00:00:00+00:00', ?, 55, 'Neutral', 'Medium', 80, '[]', '[]', '[]')
            """,
            (asset,),
        )
        connection.commit()
