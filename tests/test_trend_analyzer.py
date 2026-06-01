from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from analytics.trend_analyzer import TrendAnalyzer
from database.init_db import initialize_database


def test_trend_analyzer_returns_insufficient_history(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    _insert_market_snapshot(database_path, "BTC", "price", {"price": 100.0})

    trends = TrendAnalyzer(database_path).analyze_all()

    assert trends["btc_price"].status == "INSUFFICIENT_HISTORY"
    assert trends["btc_price"].latest_value == 100.0
    assert trends["btc_price"].direction == "unknown"


def test_trend_analyzer_detects_btc_open_interest_with_falling_price(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    _insert_market_snapshot(database_path, "BTC", "price", {"price": 110.0})
    _insert_market_snapshot(database_path, "BTC", "open_interest", {"open_interest": 1000.0})
    _insert_market_snapshot(database_path, "BTC", "price", {"price": 100.0})
    _insert_market_snapshot(database_path, "BTC", "open_interest", {"open_interest": 1200.0})

    trends = TrendAnalyzer(database_path).analyze_all()

    assert trends["btc_price"].status == "OK"
    assert trends["btc_price"].direction == "falling"
    assert trends["btc_open_interest"].status == "OK"
    assert trends["btc_open_interest"].direction == "rising"
    assert "possible bearish pressure" in trends["btc_open_interest"].reason


def test_trend_analyzer_detects_gold_real_yield_pressure(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    _insert_market_snapshot(database_path, "Gold", "real_yield", {"latest_value": 1.7})
    _insert_market_snapshot(database_path, "Gold", "real_yield", {"latest_value": 1.9})

    trends = TrendAnalyzer(database_path).analyze_all()

    assert trends["gold_real_yield"].status == "OK"
    assert trends["gold_real_yield"].direction == "rising"
    assert "pressures gold" in trends["gold_real_yield"].reason


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
