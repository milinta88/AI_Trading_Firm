from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from analytics.research_readiness import ResearchReadinessAnalyzer
from core.config import ResearchReadinessConfig
from database.init_db import initialize_database


def test_research_readiness_handles_missing_btc_sources(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    _insert_workflow_run(database_path)
    now = datetime.now(UTC)
    _seed_btc_series(database_path, "price", 10, now, lambda index: {"price": 100 + index})
    _seed_btc_series(
        database_path,
        "fear_and_greed_index",
        10,
        now,
        lambda index: {"value": 40 + index, "classification": "Neutral"},
    )

    result = ResearchReadinessAnalyzer(database_path, _test_config()).analyze_all()["BTC"]

    assert result.readiness_score == 55
    assert result.regime == "TREND_UP"
    assert result.decision_ready is False
    assert "BTC Funding Rate" in result.missing_sources
    assert "BTC Open Interest" in result.missing_sources
    assert any("Missing sources:" in reason for reason in result.no_trade_reasons)


def test_research_readiness_returns_insufficient_data_when_snapshot_history_is_short(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    _insert_workflow_run(database_path)
    now = datetime.now(UTC)
    _seed_btc_series(database_path, "price", 5, now, lambda index: {"price": 100 + index})
    _seed_btc_series(
        database_path,
        "fear_and_greed_index",
        5,
        now,
        lambda index: {"value": 50 + index, "classification": "Neutral"},
    )
    _seed_btc_series(database_path, "funding_rate", 5, now, lambda index: {"funding_rate": 0.0001 + index / 100000})
    _seed_btc_series(database_path, "open_interest", 5, now, lambda index: {"open_interest": 1000 + index * 10})

    result = ResearchReadinessAnalyzer(database_path, _test_config()).analyze_all()["BTC"]

    assert result.regime == "INSUFFICIENT_DATA"
    assert result.readiness_score == 55
    assert result.decision_ready is False
    assert any("requires at least 10 persisted OK BTC price snapshots" in reason for reason in result.no_trade_reasons)


def test_research_readiness_marks_stale_sources_and_reduces_score(tmp_path: Path) -> None:
    database_path = tmp_path / "database.db"
    initialize_database(database_path)
    _insert_workflow_run(database_path)
    now = datetime.now(UTC)
    stale_time = now - timedelta(hours=10)
    _seed_btc_series(database_path, "price", 10, now, lambda index: {"price": 100 + index})
    _seed_btc_series(
        database_path,
        "fear_and_greed_index",
        10,
        now,
        lambda index: {"value": 45 + index, "classification": "Neutral"},
    )
    _seed_btc_series(
        database_path,
        "funding_rate",
        10,
        stale_time,
        lambda index: {"funding_rate": 0.0002 + index / 100000},
    )
    _seed_btc_series(
        database_path,
        "open_interest",
        10,
        stale_time,
        lambda index: {"open_interest": 1200 + index * 10},
    )

    result = ResearchReadinessAnalyzer(database_path, _test_config()).analyze_all()["BTC"]

    assert result.readiness_score == 55
    assert result.decision_ready is False
    assert "BTC Funding Rate" in result.stale_sources
    assert "BTC Open Interest" in result.stale_sources
    assert any("Stale sources:" in reason for reason in result.no_trade_reasons)


def _test_config() -> ResearchReadinessConfig:
    return ResearchReadinessConfig(
        enabled=True,
        min_snapshots_for_regime=10,
        stale_after_minutes={
            "btc_price": 60,
            "btc_derivatives": 240,
            "fear_and_greed": 1440,
            "gold_macro": 4320,
        },
        min_readiness_score_for_decision=70,
    )


def _insert_workflow_run(database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-06-01', 'research', 'COMPLETED')
            """
        )


def _seed_btc_series(
    database_path: Path,
    data_type: str,
    count: int,
    newest_timestamp: datetime,
    payload_builder,
) -> None:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        for index in range(count):
            timestamp = newest_timestamp - timedelta(minutes=(count - index))
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
                    "BTC",
                    "test",
                    data_type,
                    json.dumps(payload_builder(index)),
                    "OK",
                    None,
                ),
            )

