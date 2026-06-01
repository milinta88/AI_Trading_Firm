from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from core.models import AnalysisResult
from database.init_db import initialize_database
from database.repository import WorkflowRepository
from scoring.models import ScoreComponent


def test_score_snapshot_persists_to_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "scores.db"
    initialize_database(database_path)
    repository = WorkflowRepository(database_path)
    workflow_run_id = repository.create_workflow_run(run_date=date(2026, 5, 28), mode="research")

    repository.store_score_snapshot(
        workflow_run_id,
        AnalysisResult(
            asset="BTC",
            total_score=68,
            bias="Bullish",
            confidence="Medium",
            data_completeness=50,
            components=[ScoreComponent("BTC Price", "OK", 100000.0, 5, 5, "Price available.")],
            reasons=["Constructive sentiment."],
            warnings=["Funding rate not configured."],
        ),
    )

    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            "SELECT asset, total_score, bias, confidence, data_completeness FROM score_snapshots"
        ).fetchone()

    assert row == ("BTC", 68, "Bullish", "Medium", 50)
