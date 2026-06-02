from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from core.models import HypothesisOutcome
from database.init_db import initialize_database
from database.repository import WorkflowRepository


def test_strategy_hypothesis_outcome_persistence_works(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    repository = WorkflowRepository(database_path)
    outcome = HypothesisOutcome(
        hypothesis_id=11,
        workflow_run_id=7,
        asset="BTC",
        hypothesis_name="BTC Trend Continuation Research Hypothesis",
        direction_bias="LONG",
        strategy_family="BTC_TREND_CONTINUATION",
        horizon_hours=24,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        evaluated_at=datetime(2026, 6, 2, tzinfo=UTC),
        entry_reference_price=100.0,
        followup_price=101.5,
        move_pct=1.5,
        max_favorable_move_pct=2.0,
        max_adverse_move_pct=0.5,
        outcome_status="FAVORABLE",
        reason="LONG hypothesis moved favorably.",
        warnings=[],
    )

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (7, '2026-06-01', 'research', 'COMPLETED')
            """
        )
        connection.execute(
            """
            INSERT INTO strategy_hypotheses (
                id, workflow_run_id, asset, hypothesis_name, direction_bias, regime, readiness_score, score,
                confidence, data_completeness, hypothesis_status, suggested_strategy_family,
                suggested_holding_period, reasons_json, blockers_json, warnings_json, invalidation_notes, created_at
            )
            VALUES (
                11, 7, 'BTC', 'BTC Trend Continuation Research Hypothesis', 'LONG', 'TREND_UP', 80, 65,
                'High', 100, 'ACTIVE', 'BTC_TREND_CONTINUATION', '1-5 days', '[]', '[]', '[]',
                'Invalidate later.', '2026-06-01T00:00:00+00:00'
            )
            """
        )

    repository.store_strategy_hypothesis_outcome(outcome)

    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT asset, horizon_hours, outcome_status, move_pct
            FROM strategy_hypothesis_outcomes
            WHERE hypothesis_id = 11
            """
        ).fetchone()

    assert row is not None
    assert row[0] == "BTC"
    assert row[1] == 24
    assert row[2] == "FAVORABLE"
    assert row[3] == 1.5
