from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loader_reads_paper_analytics_sections(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status, summary, report_text)
            VALUES (1, '2026-06-01', 'research', 'COMPLETED', 'paper summary', 'paper report text')
            """
        )
        connection.execute(
            """
            INSERT INTO paper_orders (
                id, workflow_run_id, asset, direction, order_type, status, signal_source,
                intended_entry, stop_loss, take_profit, risk_pct, size, reason_json, warnings_json
            )
            VALUES (1, 1, 'BTC', 'LONG', 'MARKET_SIMULATED', 'FILLED', 'btc_score', 100, 98, 104, 0.25, 10, '[]', '[]')
            """
        )
        connection.execute(
            """
            INSERT INTO paper_positions (
                id, order_id, workflow_run_id, asset, direction, entry_price, exit_price,
                stop_loss, take_profit, size, status, pnl_abs, pnl_pct, reason_json
            )
            VALUES (1, 1, 1, 'BTC', 'LONG', 100, 104, 98, 104, 10, 'CLOSED_TP', 40, 4, ?)
            """,
            (json.dumps(["Take profit hit."]),),
        )
        connection.execute(
            """
            INSERT INTO paper_trades (
                id, order_id, position_id, workflow_run_id, timestamp, asset, direction,
                entry_price, exit_price, size, pnl_abs, pnl_pct, result_status, reason_json
            )
            VALUES (1, 1, 1, 1, '2026-06-01T01:00:00+00:00', 'BTC', 'LONG', 100, 104, 10, 40, 4, 'CLOSED_TP', ?)
            """,
            (json.dumps(["Take profit hit."]),),
        )
        connection.execute(
            """
            INSERT INTO paper_equity_curve (id, timestamp, equity, realized_pnl, unrealized_pnl, drawdown_pct)
            VALUES (1, '2026-06-01T02:00:00+00:00', 10040, 40, 0, 0.5)
            """
        )
        connection.execute(
            """
            INSERT INTO paper_risk_events (workflow_run_id, asset, event_type, status, reason, details_json)
            VALUES (1, 'BTC', 'PAPER_SIGNAL_RISK_CHECK', 'REJECTED', 'Signal risk exceeds max_risk_per_trade_pct.', ?)
            """,
            (json.dumps({"review_category": "REJECTED"}),),
        )
        connection.execute(
            """
            INSERT INTO paper_run_summaries (
                workflow_run_id, status, signals_evaluated, signals_accepted, signals_rejected,
                no_trade_count, orders_opened, positions_updated, equity_snapshot_id, notes_json
            )
            VALUES (1, 'COMPLETED', 2, 1, 1, 0, 1, 1, 1, ?)
            """,
            (json.dumps(["Simulated only."]),),
        )

    data = load_dashboard_data(tmp_path)

    assert data.paper_trading_enabled is True
    assert data.paper_analytics_summary["latest_equity"] == 10_040.0
    assert data.paper_analytics_summary["profit_factor"] is None
    assert data.paper_signal_review_summary["signals_rejected"] == 1
    assert data.paper_latest_run_summary is not None
    assert data.paper_latest_run_summary["notes"] == ["Simulated only."]
    assert data.paper_recent_run_summaries[0]["signals_evaluated"] == 2
    assert data.paper_closed_positions[0]["status"] == "CLOSED_TP"
    assert data.paper_pnl_by_asset == [{"asset": "BTC", "trade_count": 1, "total_pnl": 40.0}]


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
                "paper_trading:",
                "  enabled: true",
                "  starting_equity: 10000",
            ]
        ),
        encoding="utf-8",
    )
