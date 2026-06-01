from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from core.config import PaperSignalConfig, PaperTradingConfig
from database.init_db import initialize_database
from paper_trading.paper_orchestrator import build_paper_trading_orchestrator
from paper_trading.repository import PaperTradingRepository


def test_paper_signal_reviews_create_one_normalized_row_per_asset(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)
    _seed_workflow(database_path, workflow_run_id=1)
    _seed_score_snapshot(database_path, workflow_run_id=1, asset="BTC", score=72, bias="Bullish", confidence="Medium", completeness=95)
    _seed_score_snapshot(database_path, workflow_run_id=1, asset="Gold", score=50, bias="Neutral", confidence="Low", completeness=40)
    _seed_price_snapshot(database_path, workflow_run_id=1, asset="BTC", data_type="price", value={"price": 100.0})

    repository = PaperTradingRepository(database_path)
    orchestrator = build_paper_trading_orchestrator(
        config=_paper_config(allow_long=True),
        signal_config=_signal_config(),
        repository=repository,
    )

    summary = orchestrator.run(workflow_run_id=1, run_date=date(2026, 6, 1))
    reviews = repository.fetch_signal_review_rows_for_run(1)

    assert summary.signals_evaluated == 2
    assert summary.signals_accepted == 1
    assert summary.signals_rejected == 0
    assert summary.no_trade_count == 1
    assert len(reviews) == 2
    assert {row["asset"] for row in reviews} == {"BTC", "Gold"}

    accepted_review = next(row for row in reviews if row["review_status"] == "ACCEPTED")
    no_trade_review = next(row for row in reviews if row["review_status"] == "NO_TRADE")

    assert accepted_review["signal_action"] == "LONG"
    assert _reason_codes(accepted_review["reasons_json"]) == {"SIGNAL_ACCEPTED"}
    assert no_trade_review["signal_action"] == "NO_TRADE"
    assert "BIAS_NOT_ALLOWED" in _reason_codes(no_trade_review["reasons_json"])


def test_paper_signal_reviews_reconcile_rejected_and_no_trade_counts(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    initialize_database(database_path)
    _seed_workflow(database_path, workflow_run_id=2)
    _seed_score_snapshot(database_path, workflow_run_id=2, asset="BTC", score=74, bias="Bullish", confidence="Medium", completeness=95)
    _seed_score_snapshot(database_path, workflow_run_id=2, asset="Gold", score=51, bias="Neutral", confidence="Low", completeness=45)
    _seed_price_snapshot(database_path, workflow_run_id=2, asset="BTC", data_type="price", value={"price": 100.0})

    repository = PaperTradingRepository(database_path)
    orchestrator = build_paper_trading_orchestrator(
        config=_paper_config(allow_long=False),
        signal_config=_signal_config(),
        repository=repository,
    )

    summary = orchestrator.run(workflow_run_id=2, run_date=date(2026, 6, 1))
    reviews = repository.fetch_signal_review_rows_for_run(2)

    assert summary.signals_evaluated == summary.signals_accepted + summary.signals_rejected + summary.no_trade_count
    assert summary.signals_accepted == 0
    assert summary.signals_rejected == 1
    assert summary.no_trade_count == 1
    assert len(reviews) == 2

    rejected_review = next(row for row in reviews if row["review_status"] == "REJECTED")
    assert rejected_review["signal_action"] == "LONG"
    assert _reason_codes(rejected_review["reasons_json"]) == {"RISK_REJECTED"}


def _seed_workflow(database_path: Path, workflow_run_id: int) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (?, '2026-06-01', 'research', 'COMPLETED')
            """,
            (workflow_run_id,),
        )


def _seed_score_snapshot(
    database_path: Path,
    workflow_run_id: int,
    asset: str,
    score: int,
    bias: str,
    confidence: str,
    completeness: int,
) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO score_snapshots (
                workflow_run_id, timestamp, asset, total_score, bias, confidence,
                data_completeness, components_json, reasons_json, warnings_json
            )
            VALUES (?, '2026-06-01T00:00:00+00:00', ?, ?, ?, ?, ?, '[]', '[]', '[]')
            """,
            (workflow_run_id, asset, score, bias, confidence, completeness),
        )


def _seed_price_snapshot(
    database_path: Path,
    workflow_run_id: int,
    asset: str,
    data_type: str,
    value: dict[str, float],
) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO market_snapshots (
                workflow_run_id, timestamp, asset, source, data_type, value_json, status, error_summary
            )
            VALUES (?, '2026-06-01T00:00:00+00:00', ?, 'test', ?, ?, 'OK', NULL)
            """,
            (workflow_run_id, asset, data_type, json.dumps(value)),
        )


def _paper_config(allow_long: bool) -> PaperTradingConfig:
    return PaperTradingConfig(
        enabled=True,
        starting_equity=10_000.0,
        base_currency="USD",
        max_risk_per_trade_pct=0.25,
        max_daily_loss_pct=1.0,
        max_open_positions=2,
        allow_long=allow_long,
        allow_short=True,
        fill_mode="close_price",
    )


def _signal_config() -> PaperSignalConfig:
    return PaperSignalConfig(
        profile="conservative",
        btc_long_score_threshold=70,
        btc_short_score_threshold=35,
        gold_long_score_threshold=70,
        gold_short_score_threshold=35,
        min_confidence="Medium",
        min_btc_data_completeness=80,
        min_gold_data_completeness=60,
        allow_neutral_bias=False,
        exploratory_mode=False,
    )


def _reason_codes(raw_value: str) -> set[str]:
    return {
        str(item.get("code"))
        for item in json.loads(raw_value)
        if isinstance(item, dict)
    }
