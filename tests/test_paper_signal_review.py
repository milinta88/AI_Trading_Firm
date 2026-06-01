from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from core.config import PaperTradingConfig
from database.init_db import initialize_database
from paper_trading.analytics import PaperAnalytics
from paper_trading.models import PaperSignal
from paper_trading.repository import PaperTradingRepository
from paper_trading.risk_engine import PaperRiskEngine


def test_paper_signal_review_counts_rejections_and_no_trade(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-06-01', 'research', 'COMPLETED')
            """
        )
        connection.executemany(
            """
            INSERT INTO paper_risk_events (workflow_run_id, asset, event_type, status, reason, details_json)
            VALUES (?, ?, 'PAPER_SIGNAL_RISK_CHECK', ?, ?, ?)
            """,
            [
                (1, "BTC", "APPROVED", "Paper signal passed simulated risk checks.", json.dumps({"review_category": "APPROVED"})),
                (1, "BTC", "REJECTED", "Signal risk exceeds max_risk_per_trade_pct.", json.dumps({"review_category": "REJECTED"})),
                (1, "Gold", "REJECTED", "Data quality is FAIL; simulated order rejected.", json.dumps({"review_category": "REJECTED"})),
                (1, "Gold", "SKIPPED", "Paper signal is NO_TRADE; no simulated order will be created.", json.dumps({"review_category": "NO_TRADE"})),
            ],
        )

    report = PaperAnalytics(database_path=database_path, starting_equity=10_000.0).build_report()
    review = report.signal_review

    assert review.signals_evaluated == 4
    assert review.signals_accepted == 1
    assert review.signals_rejected == 2
    assert review.no_trade_count == 1
    assert review.rejected_by_reason == {
        "Data quality is FAIL; simulated order rejected.": 1,
        "Signal risk exceeds max_risk_per_trade_pct.": 1,
    }
    assert review.rejected_by_asset == {"BTC": 1, "Gold": 1}


def test_paper_risk_engine_persists_rich_signal_review_details(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-06-01', 'research', 'COMPLETED')
            """
        )

    repository = PaperTradingRepository(database_path)
    engine = PaperRiskEngine(config=_paper_config(), repository=repository)
    signal = PaperSignal(
        asset="BTC",
        direction="LONG",
        signal_source="btc_score",
        score=68,
        bias="Bullish",
        confidence="Medium",
        data_completeness=100,
        intended_entry=100.0,
        stop_loss=98.0,
        take_profit=104.0,
        risk_pct=0.25,
        warnings=["Simulated only."],
    )

    state = engine.evaluate(
        signal=signal,
        workflow_run_id=1,
        run_date=date(2026, 6, 1),
        data_quality_status="OK",
    )

    assert state.status == "APPROVED"

    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            "SELECT status, reason, details_json FROM paper_risk_events ORDER BY id DESC LIMIT 1"
        ).fetchone()

    details = json.loads(row[2])
    assert row[0] == "APPROVED"
    assert row[1] == "Paper signal passed simulated risk checks."
    assert details["signal_source"] == "btc_score"
    assert details["direction"] == "LONG"
    assert details["score"] == 68
    assert details["bias"] == "Bullish"
    assert details["confidence"] == "Medium"
    assert details["data_completeness"] == 100
    assert details["is_trade_candidate"] is True
    assert details["review_category"] == "APPROVED"
    assert details["risk_pct"] == 0.25
    assert details["approved_size"] > 0
    assert details["simulated_only"] is True


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
