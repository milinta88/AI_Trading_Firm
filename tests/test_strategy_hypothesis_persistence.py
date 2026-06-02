from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path

from core.models import StrategyHypothesis
from database.init_db import initialize_database
from database.repository import WorkflowRepository


def test_strategy_hypothesis_persists_to_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "strategy.db"
    initialize_database(database_path)
    repository = WorkflowRepository(database_path)
    workflow_run_id = repository.create_workflow_run(run_date=date(2026, 6, 2), mode="research")

    repository.store_strategy_hypothesis(
        workflow_run_id,
        StrategyHypothesis(
            asset="BTC",
            hypothesis_name="BTC Trend Continuation Research Hypothesis",
            direction_bias="LONG",
            regime="TREND_UP",
            readiness_score=85,
            score=68,
            confidence="High",
            data_completeness=100,
            hypothesis_status="ACTIVE",
            reasons=["BTC regime is TREND_UP."],
            blockers=[],
            warnings=[],
            suggested_strategy_family="BTC_TREND_CONTINUATION",
            suggested_holding_period="1-5 days",
            invalidation_notes="Invalidate if the regime changes.",
            created_at=datetime(2026, 6, 2, tzinfo=UTC),
        ),
    )

    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT asset, direction_bias, regime, readiness_score, score, confidence, hypothesis_status
            FROM strategy_hypotheses
            """
        ).fetchone()

    assert row == ("BTC", "LONG", "TREND_UP", 85, 68, "High", "ACTIVE")
