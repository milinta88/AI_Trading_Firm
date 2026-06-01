from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loader_reads_paper_trading_rows(tmp_path: Path) -> None:
    _write_config(tmp_path, paper_enabled=True)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-05-30', 'research', 'COMPLETED')
            """
        )
        connection.execute(
            """
            INSERT INTO paper_orders (
                workflow_run_id, asset, direction, order_type, status, signal_source,
                intended_entry, stop_loss, take_profit, risk_pct, size, reason_json, warnings_json
            )
            VALUES (1, 'BTC', 'LONG', 'MARKET_SIMULATED', 'FILLED', 'test', 100, 98, 104, 0.25, 12.5, '[]', '[]')
            """
        )
        connection.execute(
            """
            INSERT INTO paper_positions (
                order_id, workflow_run_id, asset, direction, entry_price, stop_loss, take_profit,
                size, status, pnl_abs, pnl_pct, reason_json
            )
            VALUES (1, 1, 'BTC', 'LONG', 100, 98, 104, 12.5, 'OPEN', 0, 0, '[]')
            """
        )
        connection.execute(
            """
            INSERT INTO paper_equity_curve (equity, realized_pnl, unrealized_pnl, drawdown_pct)
            VALUES (10000, 0, 0, 0)
            """
        )
        connection.execute(
            """
            INSERT INTO paper_risk_events (workflow_run_id, asset, event_type, status, reason, details_json)
            VALUES (1, 'BTC', 'PAPER_SIGNAL_RISK_CHECK', 'APPROVED', 'ok', '{}')
            """
        )
        connection.commit()

    data = load_dashboard_data(tmp_path)

    assert data.paper_trading_enabled is True
    assert data.paper_latest_equity is not None
    assert data.paper_open_positions[0]["asset"] == "BTC"
    assert data.paper_recent_orders[0]["status"] == "FILLED"
    assert data.paper_recent_risk_events[0]["status"] == "APPROVED"


def _write_config(tmp_path: Path, paper_enabled: bool) -> None:
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
                f"  enabled: {'true' if paper_enabled else 'false'}",
            ]
        ),
        encoding="utf-8",
    )
