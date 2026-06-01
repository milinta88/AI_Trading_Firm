from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from database.init_db import initialize_database
from paper_trading.models import PaperOrder, PaperPosition
from paper_trading.repository import PaperTradingRepository


def test_paper_repository_stores_order_position_and_price(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)
    _insert_workflow_and_price(database_path)
    repository = PaperTradingRepository(database_path)

    order_id = repository.store_order(
        1,
        PaperOrder(
            asset="BTC",
            direction="LONG",
            order_type="MARKET_SIMULATED",
            status="FILLED",
            signal_source="test",
            intended_entry=100.0,
            stop_loss=98.0,
            take_profit=104.0,
            risk_pct=0.25,
            size=12.5,
            reasons=["simulated"],
            warnings=["no real execution"],
        ),
    )
    position_id = repository.create_position(
        1,
        order_id,
        PaperPosition(
            asset="BTC",
            direction="LONG",
            entry_price=100.0,
            stop_loss=98.0,
            take_profit=104.0,
            size=12.5,
            status="OPEN",
        ),
    )

    assert order_id == 1
    assert position_id == 1
    assert repository.count_open_positions() == 1
    assert repository.fetch_latest_market_price("BTC") == 100.0
    assert repository.fetch_open_positions()[0].asset == "BTC"


def _insert_workflow_and_price(database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-05-30', 'research', 'COMPLETED')
            """
        )
        connection.execute(
            """
            INSERT INTO market_snapshots (
                workflow_run_id, timestamp, asset, source, data_type, value_json, status, error_summary
            )
            VALUES (1, '2026-05-30T00:00:00+00:00', 'BTC', 'test', 'price', ?, 'OK', NULL)
            """,
            (json.dumps({"price": 100.0}),),
        )
        connection.commit()
