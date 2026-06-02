from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from analytics.hypothesis_outcomes import HypothesisOutcomeEvaluator
from core.config import HypothesisOutcomeConfig
from database.init_db import initialize_database


def test_long_favorable_outcome(tmp_path: Path) -> None:
    outcome = _evaluate_single_outcome(
        tmp_path=tmp_path,
        asset="BTC",
        direction_bias="LONG",
        hypothesis_status="ACTIVE",
        entry_price=100.0,
        followup_price=101.0,
    )

    assert outcome.outcome_status == "FAVORABLE"
    assert outcome.move_pct == 1.0


def test_long_unfavorable_outcome(tmp_path: Path) -> None:
    outcome = _evaluate_single_outcome(
        tmp_path=tmp_path,
        asset="BTC",
        direction_bias="LONG",
        hypothesis_status="ACTIVE",
        entry_price=100.0,
        followup_price=99.0,
    )

    assert outcome.outcome_status == "UNFAVORABLE"
    assert outcome.move_pct == -1.0


def test_short_favorable_outcome(tmp_path: Path) -> None:
    outcome = _evaluate_single_outcome(
        tmp_path=tmp_path,
        asset="BTC",
        direction_bias="SHORT",
        hypothesis_status="ACTIVE",
        entry_price=100.0,
        followup_price=99.0,
    )

    assert outcome.outcome_status == "FAVORABLE"
    assert outcome.move_pct == -1.0


def test_short_unfavorable_outcome(tmp_path: Path) -> None:
    outcome = _evaluate_single_outcome(
        tmp_path=tmp_path,
        asset="BTC",
        direction_bias="SHORT",
        hypothesis_status="ACTIVE",
        entry_price=100.0,
        followup_price=101.0,
    )

    assert outcome.outcome_status == "UNFAVORABLE"
    assert outcome.move_pct == 1.0


def test_neutral_threshold_behavior(tmp_path: Path) -> None:
    outcome = _evaluate_single_outcome(
        tmp_path=tmp_path,
        asset="BTC",
        direction_bias="LONG",
        hypothesis_status="ACTIVE",
        entry_price=100.0,
        followup_price=100.2,
    )

    assert outcome.outcome_status == "NEUTRAL"
    assert outcome.move_pct == 0.2


def test_insufficient_followup_data(tmp_path: Path) -> None:
    database_path = _prepare_database(tmp_path)
    created_at = datetime(2026, 6, 1, tzinfo=UTC)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        _insert_workflow_run(connection)
        _insert_hypothesis(
            connection,
            asset="BTC",
            direction_bias="LONG",
            hypothesis_status="ACTIVE",
            created_at=created_at,
        )
        _insert_market_snapshot(connection, "BTC", "price", 100.0, created_at)

    evaluator = HypothesisOutcomeEvaluator(_test_config(), database_path)
    outcomes = evaluator.evaluate_pending(now=datetime(2026, 6, 2, 1, tzinfo=UTC))

    assert len(outcomes) == 1
    assert outcomes[0].outcome_status == "INSUFFICIENT_FOLLOWUP_DATA"


def test_blocked_hypothesis_not_evaluated(tmp_path: Path) -> None:
    outcome = _evaluate_single_outcome(
        tmp_path=tmp_path,
        asset="Gold",
        direction_bias="NO_TRADE",
        hypothesis_status="BLOCKED",
        entry_price=2500.0,
        followup_price=2510.0,
    )

    assert outcome.outcome_status == "BLOCKED_NOT_EVALUATED"


def _evaluate_single_outcome(
    *,
    tmp_path: Path,
    asset: str,
    direction_bias: str,
    hypothesis_status: str,
    entry_price: float,
    followup_price: float,
):
    database_path = _prepare_database(tmp_path)
    created_at = datetime(2026, 6, 1, tzinfo=UTC)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        _insert_workflow_run(connection)
        _insert_hypothesis(
            connection,
            asset=asset,
            direction_bias=direction_bias,
            hypothesis_status=hypothesis_status,
            created_at=created_at,
        )
        _insert_market_snapshot(connection, asset, _data_type_for_asset(asset), entry_price, created_at)
        _insert_market_snapshot(connection, asset, _data_type_for_asset(asset), followup_price, datetime(2026, 6, 2, tzinfo=UTC))

    evaluator = HypothesisOutcomeEvaluator(_test_config(), database_path)
    outcomes = evaluator.evaluate_pending(now=datetime(2026, 6, 2, 1, tzinfo=UTC))

    assert len(outcomes) == 1
    return outcomes[0]


def _prepare_database(tmp_path: Path) -> Path:
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)
    return database_path


def _test_config() -> HypothesisOutcomeConfig:
    return HypothesisOutcomeConfig(
        enabled=True,
        horizons_hours=[24],
        neutral_move_pct={"BTC": 0.25, "Gold": 0.20},
        max_lookback_days=14,
    )


def _insert_workflow_run(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO workflow_runs (id, run_date, mode, status)
        VALUES (1, '2026-06-01', 'research', 'COMPLETED')
        """
    )


def _insert_hypothesis(
    connection: sqlite3.Connection,
    *,
    asset: str,
    direction_bias: str,
    hypothesis_status: str,
    created_at: datetime,
) -> None:
    family = "BTC_TREND_CONTINUATION" if asset == "BTC" else "GOLD_MACRO_PRESSURE"
    connection.execute(
        """
        INSERT INTO strategy_hypotheses (
            workflow_run_id, asset, hypothesis_name, direction_bias, regime, readiness_score, score,
            confidence, data_completeness, hypothesis_status, suggested_strategy_family,
            suggested_holding_period, reasons_json, blockers_json, warnings_json, invalidation_notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            asset,
            f"{asset} Test Hypothesis",
            direction_bias,
            "TREND_UP" if asset == "BTC" else "MIXED",
            80,
            65,
            "High",
            100,
            hypothesis_status,
            family,
            "1-3 days",
            json.dumps(["Reason"]),
            json.dumps([]),
            json.dumps([]),
            "Invalidate later.",
            created_at.isoformat(),
        ),
    )


def _insert_market_snapshot(
    connection: sqlite3.Connection,
    asset: str,
    data_type: str,
    price: float,
    timestamp: datetime,
) -> None:
    payload = {"price": price} if asset == "BTC" else {"latest_value": price, "quote_timestamp": timestamp.isoformat()}
    connection.execute(
        """
        INSERT INTO market_snapshots (
            workflow_run_id, timestamp, asset, source, data_type, value_json, status, error_summary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            timestamp.isoformat(),
            asset,
            "test",
            data_type,
            json.dumps(payload),
            "OK",
            None,
        ),
    )


def _data_type_for_asset(asset: str) -> str:
    return "price" if asset == "BTC" else "spot_price"
