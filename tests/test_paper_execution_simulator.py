from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from core.config import PaperTradingConfig
from database.init_db import initialize_database
from paper_trading.execution_simulator import PaperExecutionSimulator
from paper_trading.models import PaperRiskState, PaperSignal
from paper_trading.repository import PaperTradingRepository


def test_paper_execution_simulator_opens_position_from_persisted_price(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)
    _insert_workflow_and_price(database_path, price=101.0)
    repository = PaperTradingRepository(database_path)
    simulator = PaperExecutionSimulator(_paper_config(), repository)

    result = simulator.simulate_order(workflow_run_id=1, signal=_signal(), risk_state=_approved_risk())

    assert result.status == "OPENED"
    assert result.entry_price == 101.0
    assert repository.count_open_positions() == 1
    assert repository.fetch_recent_order_rows()[0]["status"] == "FILLED"


def test_paper_execution_simulator_stores_equity_curve(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)
    _insert_workflow_and_price(database_path, price=101.0)
    repository = PaperTradingRepository(database_path)
    simulator = PaperExecutionSimulator(_paper_config(), repository)
    simulator.simulate_order(workflow_run_id=1, signal=_signal(), risk_state=_approved_risk())

    equity_id = simulator.store_equity_curve_snapshot()

    assert equity_id == 1
    assert repository.fetch_equity_curve_rows()[0]["equity"] == 10_000


def _insert_workflow_and_price(database_path: Path, price: float) -> None:
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
            (json.dumps({"price": price}),),
        )


def _signal() -> PaperSignal:
    return PaperSignal(
        asset="BTC",
        direction="LONG",
        signal_source="test",
        score=72,
        bias="Bullish",
        confidence="Medium",
        data_completeness=90,
        intended_entry=100.0,
        stop_loss=98.0,
        take_profit=104.0,
        risk_pct=0.25,
    )


def _approved_risk() -> PaperRiskState:
    return PaperRiskState(
        approved=True,
        status="APPROVED",
        reason_code="SIGNAL_ACCEPTED",
        reason="ok",
        equity=10_000.0,
        daily_realized_pnl=0.0,
        daily_loss_pct=0.0,
        open_positions_count=0,
        approved_size=12.5,
        risk_amount=25.0,
    )


def _paper_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        enabled=True,
        starting_equity=10_000.0,
        base_currency="USD",
        max_risk_per_trade_pct=0.25,
        max_daily_loss_pct=1.0,
        max_open_positions=2,
        allow_long=True,
        allow_short=True,
        fill_mode="close_price",
    )
