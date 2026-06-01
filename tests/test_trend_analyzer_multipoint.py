from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from analytics.trend_analyzer import TrendAnalyzer
from database.init_db import initialize_database


def test_multipoint_trend_detects_strong_rising_btc_price(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    for price in [100.0, 102.0, 104.0, 108.0, 112.0]:
        _insert_market_snapshot(database_path, "BTC", "price", {"price": price})

    trends = TrendAnalyzer(database_path).analyze_all_multipoint()

    btc_price = trends["btc_price"]
    assert btc_price.status == "OK"
    assert btc_price.first_value == 100.0
    assert btc_price.latest_value == 112.0
    assert btc_price.direction == "rising"
    assert btc_price.trend_strength == "strong"
    assert btc_price.lookback_points == 5


def test_multipoint_trend_detects_mixed_direction(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    for value in [50.0, 55.0, 53.0, 57.0]:
        _insert_market_snapshot(database_path, "BTC", "fear_and_greed_index", {"value": value})

    trends = TrendAnalyzer(database_path).analyze_all_multipoint()

    fear_greed = trends["btc_fear_greed"]
    assert fear_greed.status == "OK"
    assert fear_greed.direction == "mixed"
    assert fear_greed.trend_strength in {"weak", "moderate"}


def test_multipoint_trend_requires_three_usable_points(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    for value in [1_000.0, 1_100.0]:
        _insert_market_snapshot(database_path, "BTC", "open_interest", {"open_interest": value})

    trends = TrendAnalyzer(database_path).analyze_all_multipoint()

    open_interest = trends["btc_open_interest"]
    assert open_interest.status == "INSUFFICIENT_HISTORY"
    assert open_interest.lookback_points == 2
    assert open_interest.direction == "unknown"


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
