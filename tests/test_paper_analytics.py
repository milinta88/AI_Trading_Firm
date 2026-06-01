from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from database.init_db import initialize_database
from paper_trading.analytics import PaperAnalytics


def test_paper_analytics_calculates_performance_metrics(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)
    _seed_paper_analytics_data(database_path)

    report = PaperAnalytics(database_path=database_path, starting_equity=10_000.0).build_report(limit=10)
    performance = report.performance
    pnl_by_asset = {row["asset"]: row["total_pnl"] for row in report.pnl_by_asset}

    assert report.database_available is True
    assert performance.starting_equity == 10_000.0
    assert performance.latest_equity == 10_050.0
    assert performance.total_pnl_abs == 50.0
    assert performance.total_pnl_pct == 0.5
    assert performance.max_drawdown_pct == 1.75
    assert performance.total_orders == 3
    assert performance.open_positions == 1
    assert performance.closed_positions == 2
    assert performance.total_trades == 2
    assert performance.winning_trades == 1
    assert performance.losing_trades == 1
    assert performance.win_rate == 50.0
    assert performance.gross_profit == 40.0
    assert performance.gross_loss == 25.0
    assert abs((performance.profit_factor or 0.0) - 1.6) < 1e-9
    assert performance.average_pnl == 7.5
    assert abs((performance.average_r_multiple or 0.0) - 0.75) < 1e-9
    assert pnl_by_asset == {"BTC": 40.0, "Gold": -25.0}
    assert report.latest_run_summary is not None
    assert report.latest_run_summary["workflow_run_id"] == 1
    assert report.latest_run_summary["notes"] == ["Simulated only."]
    assert report.recent_closed_positions[0]["reasons"]


def test_paper_analytics_handles_missing_database_safely(tmp_path: Path) -> None:
    missing_database = tmp_path / "missing.db"

    report = PaperAnalytics(database_path=missing_database, starting_equity=10_000.0).build_report()

    assert report.database_available is False
    assert "Database not found" in report.message
    assert report.performance.latest_equity == 10_000.0
    assert report.signal_review.signals_evaluated == 0


def _seed_paper_analytics_data(database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-06-01', 'research', 'COMPLETED')
            """
        )
        connection.executemany(
            """
            INSERT INTO paper_orders (
                id, workflow_run_id, asset, direction, order_type, status, signal_source,
                intended_entry, stop_loss, take_profit, risk_pct, size, reason_json, warnings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1, "BTC", "LONG", "MARKET_SIMULATED", "FILLED", "btc_score", 100.0, 98.0, 104.0, 0.25, 10.0, "[]", "[]"),
                (2, 1, "Gold", "SHORT", "MARKET_SIMULATED", "FILLED", "gold_score", 200.0, 210.0, 180.0, 0.25, 5.0, "[]", "[]"),
                (3, 1, "BTC", "LONG", "MARKET_SIMULATED", "FILLED", "btc_score", 101.0, 99.0, 106.0, 0.25, 8.0, "[]", "[]"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO paper_positions (
                id, order_id, workflow_run_id, asset, direction, entry_price, exit_price,
                stop_loss, take_profit, size, status, pnl_abs, pnl_pct, reason_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1, 1, "BTC", "LONG", 100.0, 104.0, 98.0, 104.0, 10.0, "CLOSED_TP", 40.0, 4.0, json.dumps(["Take profit hit."])),
                (2, 2, 1, "Gold", "SHORT", 200.0, 205.0, 210.0, 180.0, 5.0, "CLOSED_STOP", -25.0, -2.5, json.dumps(["Stopped out."])),
                (3, 3, 1, "BTC", "LONG", 101.0, None, 99.0, 106.0, 8.0, "OPEN", 0.0, 0.0, json.dumps(["Monitoring open paper position."])),
            ],
        )
        connection.executemany(
            """
            INSERT INTO paper_trades (
                id, order_id, position_id, workflow_run_id, timestamp, asset, direction,
                entry_price, exit_price, size, pnl_abs, pnl_pct, result_status, reason_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1, 1, 1, "2026-06-01T00:00:00+00:00", "BTC", "LONG", 100.0, 104.0, 10.0, 40.0, 4.0, "CLOSED_TP", json.dumps(["Take profit hit."])),
                (2, 2, 2, 1, "2026-06-01T01:00:00+00:00", "Gold", "SHORT", 200.0, 205.0, 5.0, -25.0, -2.5, "CLOSED_STOP", json.dumps(["Stopped out."])),
            ],
        )
        connection.executemany(
            """
            INSERT INTO paper_equity_curve (id, timestamp, equity, realized_pnl, unrealized_pnl, drawdown_pct)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "2026-06-01T00:00:00+00:00", 10_000.0, 0.0, 0.0, 0.0),
                (2, "2026-06-01T01:00:00+00:00", 9_950.0, -25.0, 0.0, 1.75),
                (3, "2026-06-01T02:00:00+00:00", 10_050.0, 15.0, 35.0, 1.25),
            ],
        )
        connection.execute(
            """
            INSERT INTO paper_run_summaries (
                workflow_run_id, status, signals_evaluated, signals_accepted, signals_rejected,
                no_trade_count, orders_opened, positions_updated, equity_snapshot_id, notes_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "COMPLETED", 4, 1, 2, 1, 1, 1, 3, json.dumps(["Simulated only."])),
        )
