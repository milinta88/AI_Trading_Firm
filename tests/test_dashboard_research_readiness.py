from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loader_handles_missing_research_readiness_table(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("DROP TABLE research_readiness_snapshots")

    data = load_dashboard_data(tmp_path)

    assert data.database_available is True
    assert data.research_readiness_enabled is True
    assert {row["asset"] for row in data.latest_research_readiness} == {"BTC", "Gold"}
    assert data.recent_research_readiness == []


def test_dashboard_loader_reads_persisted_research_readiness_history(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-06-01', 'research', 'COMPLETED')
            """
        )
        connection.execute(
            """
            INSERT INTO research_readiness_snapshots (
                workflow_run_id, asset, readiness_score, regime, data_completeness, decision_ready,
                stale_sources_json, missing_sources_json, warnings_json, no_trade_reasons_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "BTC",
                82,
                "TREND_UP",
                100,
                1,
                json.dumps([]),
                json.dumps([]),
                json.dumps(["Read-only regime classification from persisted snapshots."]),
                json.dumps([]),
                datetime(2026, 6, 1, 1, 0, tzinfo=UTC).isoformat(),
            ),
        )

    data = load_dashboard_data(tmp_path)

    assert data.latest_research_readiness[0]["asset"] == "BTC"
    assert data.latest_research_readiness[0]["decision_ready"] is True
    assert data.recent_research_readiness[0]["regime"] == "TREND_UP"


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
                "research_readiness:",
                "  enabled: true",
                "  min_snapshots_for_regime: 10",
                "  stale_after_minutes:",
                "    btc_price: 60",
                "    btc_derivatives: 240",
                "    fear_and_greed: 1440",
                "    gold_macro: 4320",
                "  min_readiness_score_for_decision: 70",
            ]
        ),
        encoding="utf-8",
    )

