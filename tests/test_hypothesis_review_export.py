from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from analytics.hypothesis_review_export import (
    HypothesisReviewExportService,
    HYPOTHESIS_OUTCOME_HEADERS,
    HYPOTHESIS_REVIEW_SUMMARY_HEADERS,
    STRATEGY_HYPOTHESIS_HEADERS,
)
from database.init_db import initialize_database


def test_export_empty_tables_returns_headers(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)
    service = HypothesisReviewExportService(database_path)

    hypotheses_csv = service.export_strategy_hypotheses_csv()
    outcomes_csv = service.export_hypothesis_outcomes_csv()
    summaries_csv = service.export_review_summaries_csv()

    assert hypotheses_csv.splitlines()[0] == ",".join(STRATEGY_HYPOTHESIS_HEADERS)
    assert outcomes_csv.splitlines()[0] == ",".join(HYPOTHESIS_OUTCOME_HEADERS)
    assert summaries_csv.splitlines()[0] == ",".join(HYPOTHESIS_REVIEW_SUMMARY_HEADERS)


def test_export_populated_outcomes_and_write_files(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)
    service = HypothesisReviewExportService(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "INSERT INTO workflow_runs (id, run_date, mode, status) VALUES (1, '2026-06-02', 'research', 'COMPLETED')"
        )
        connection.execute(
            """
            INSERT INTO strategy_hypotheses (
                id, workflow_run_id, asset, hypothesis_name, direction_bias, regime, readiness_score, score,
                confidence, data_completeness, hypothesis_status, suggested_strategy_family,
                suggested_holding_period, reasons_json, blockers_json, warnings_json, invalidation_notes, created_at
            )
            VALUES (1, 1, 'BTC', 'BTC Trend', 'LONG', 'TREND_UP', 85, 72, 'Medium', 100, 'ACTIVE',
                    'BTC_TREND_CONTINUATION', '1-3 days', '[]', '[]', '[]', 'Invalidate', ?)
            """,
            (datetime(2026, 6, 2, tzinfo=UTC).isoformat(),),
        )
        connection.execute(
            """
            INSERT INTO strategy_hypothesis_outcomes (
                hypothesis_id, workflow_run_id, asset, hypothesis_name, direction_bias, strategy_family,
                horizon_hours, created_at, evaluated_at, entry_reference_price, followup_price, move_pct,
                max_favorable_move_pct, max_adverse_move_pct, outcome_status, reason, warnings_json
            )
            VALUES (1, 1, 'BTC', 'BTC Trend', 'LONG', 'BTC_TREND_CONTINUATION', 24, ?, ?, 100.0, 102.0, 2.0, 2.5, 0.8, 'FAVORABLE', 'Follow-up was favorable.', '[]')
            """,
            (
                datetime(2026, 6, 2, tzinfo=UTC).isoformat(),
                datetime(2026, 6, 3, tzinfo=UTC).isoformat(),
            ),
        )

    outcomes_csv = service.export_hypothesis_outcomes_csv()
    assert "BTC_TREND_CONTINUATION" in outcomes_csv
    assert "FAVORABLE" in outcomes_csv

    export_dir = tmp_path / "exports"
    artifacts = service.write_review_exports(export_dir, timestamp=datetime(2026, 6, 2, 1, 2, 3))

    assert len(artifacts) == 3
    assert artifacts[0].path.exists()
    assert artifacts[1].path.exists()
    assert artifacts[2].path.exists()
