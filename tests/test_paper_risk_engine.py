from __future__ import annotations

from datetime import date
from pathlib import Path

from core.config import PaperTradingConfig
from database.init_db import initialize_database
from paper_trading.models import PaperSignal
from paper_trading.repository import PaperTradingRepository
from paper_trading.risk_engine import PaperRiskEngine


def test_paper_risk_engine_rejects_when_disabled(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)
    repository = PaperTradingRepository(database_path)
    engine = PaperRiskEngine(_paper_config(enabled=False), repository)

    state = engine.evaluate(_trade_signal(), workflow_run_id=None, run_date=date(2026, 5, 30), data_quality_status="WARNING")

    assert state.approved is False
    assert state.status == "REJECTED"
    assert "disabled" in state.reason
    assert repository.fetch_recent_risk_event_rows()[0]["status"] == "REJECTED"


def test_paper_risk_engine_approves_safe_signal_and_sizes_position(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)
    repository = PaperTradingRepository(database_path)
    engine = PaperRiskEngine(_paper_config(enabled=True), repository)

    state = engine.evaluate(_trade_signal(), workflow_run_id=None, run_date=date(2026, 5, 30), data_quality_status="WARNING")

    assert state.approved is True
    assert state.status == "APPROVED"
    assert state.risk_amount == 25.0
    assert state.approved_size == 12.5


def _trade_signal() -> PaperSignal:
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
        reasons=["test"],
        warnings=["simulated only"],
    )


def _paper_config(enabled: bool) -> PaperTradingConfig:
    return PaperTradingConfig(
        enabled=enabled,
        starting_equity=10_000.0,
        base_currency="USD",
        max_risk_per_trade_pct=0.25,
        max_daily_loss_pct=1.0,
        max_open_positions=2,
        allow_long=True,
        allow_short=True,
        fill_mode="close_price",
    )
