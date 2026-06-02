from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loader_handles_missing_strategy_hypotheses_table(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("DROP TABLE strategy_hypotheses")

    data = load_dashboard_data(tmp_path)

    assert data.strategy_hypotheses_enabled is True
    assert data.latest_strategy_hypotheses == []
    assert data.recent_strategy_hypotheses == []


def test_dashboard_loader_reads_latest_strategy_hypotheses(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-06-02', 'research', 'COMPLETED')
            """
        )
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
                "BTC",
                "BTC Trend Continuation Research Hypothesis",
                "LONG",
                "TREND_UP",
                82,
                66,
                "High",
                100,
                "ACTIVE",
                "BTC_TREND_CONTINUATION",
                "1-5 days",
                json.dumps(["BTC regime is TREND_UP."]),
                json.dumps([]),
                json.dumps([]),
                "Invalidate if the regime changes.",
                "2026-06-02T00:00:00+00:00",
            ),
        )

    data = load_dashboard_data(tmp_path)

    assert data.latest_strategy_hypotheses[0]["asset"] == "BTC"
    assert data.latest_strategy_hypotheses[0]["direction_bias"] == "LONG"
    assert data.recent_strategy_hypotheses[0]["suggested_strategy_family"] == "BTC_TREND_CONTINUATION"


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "\n".join(
            [
                "app:",
                "  name: AI Trading Firm",
                "  mode: research",
                "database:",
                "  path: data/database.db",
                "risk:",
                "  execution_enabled: false",
                "strategy_hypotheses:",
                "  enabled: true",
                "  min_readiness_score: 70",
                "  min_confidence: Medium",
                "  allow_watch_when_not_ready: true",
            ]
        ),
        encoding="utf-8",
    )
