from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import dashboard.app as dashboard_app
from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loader_handles_missing_hypothesis_review_summary_table(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("DROP TABLE hypothesis_review_summaries")

    data = load_dashboard_data(tmp_path)

    assert data.hypothesis_review_enabled is True
    assert data.latest_hypothesis_review_summary is not None
    assert data.latest_hypothesis_review_summary["total_outcomes"] == 0
    assert data.hypothesis_review_outcomes == []
    assert data.hypothesis_review_notes == []


def test_dashboard_loader_reads_latest_hypothesis_review_summary(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO hypothesis_review_summaries (
                created_at, lookback_days, total_outcomes, evaluated_outcomes, favorable_count,
                unfavorable_count, neutral_count, insufficient_followup_count, blocked_not_evaluated_count,
                favorable_rate, unfavorable_rate, neutral_rate, by_asset_json, by_strategy_family_json,
                by_regime_json, by_horizon_json, by_readiness_bucket_json, by_hypothesis_status_json,
                avg_move_pct, avg_max_favorable_move_pct, avg_max_adverse_move_pct,
                promoted_candidates_json, blocked_candidates_json, candidate_progress_json, warnings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-02T00:00:00+00:00",
                14,
                12,
                10,
                6,
                2,
                2,
                1,
                1,
                0.6,
                0.2,
                0.2,
                json.dumps([{"asset": "BTC", "evaluated_outcomes": 10}]),
                json.dumps([{"strategy_family": "BTC_TREND_CONTINUATION", "evaluated_outcomes": 10}]),
                json.dumps([{"regime": "TREND_UP", "evaluated_outcomes": 10}]),
                json.dumps([{"horizon_hours": 24, "evaluated_outcomes": 10}]),
                json.dumps([{"readiness_bucket": "HIGH", "evaluated_outcomes": 10}]),
                json.dumps([{"hypothesis_status": "ACTIVE", "evaluated_outcomes": 10}]),
                0.5,
                1.2,
                0.4,
                json.dumps([{"strategy_family": "BTC_TREND_CONTINUATION", "asset": "BTC"}]),
                json.dumps([]),
                json.dumps([{"strategy_family": "BTC_TREND_CONTINUATION", "candidate_status": "REVIEW_CANDIDATE"}]),
                json.dumps([]),
            ),
        )

    data = load_dashboard_data(tmp_path)

    assert data.latest_hypothesis_review_summary is not None
    assert data.latest_hypothesis_review_summary["evaluated_outcomes"] == 10
    assert data.latest_hypothesis_review_summary["promoted_candidates"][0]["strategy_family"] == "BTC_TREND_CONTINUATION"
    assert data.latest_hypothesis_review_summary["candidate_progress"][0]["candidate_status"] == "REVIEW_CANDIDATE"


def test_dashboard_review_filters_handle_empty_rows() -> None:
    assert dashboard_app._filter_hypothesis_review_rows([], asset="BTC", outcome_status="FAVORABLE") == []


def test_dashboard_review_filters_can_drill_down_by_family_and_status() -> None:
    rows = [
        {
            "asset": "BTC",
            "strategy_family": "BTC_TREND_CONTINUATION",
            "regime": "TREND_UP",
            "readiness_bucket": "HIGH",
            "hypothesis_status": "ACTIVE",
            "horizon_hours": 24,
            "outcome_status": "FAVORABLE",
            "created_at": datetime(2026, 6, 2, tzinfo=UTC).isoformat(),
        },
        {
            "asset": "Gold",
            "strategy_family": "GOLD_NO_TRADE",
            "regime": "MIXED",
            "readiness_bucket": "MEDIUM",
            "hypothesis_status": "WATCH",
            "horizon_hours": 24,
            "outcome_status": "NEUTRAL",
            "created_at": datetime(2026, 6, 2, tzinfo=UTC).isoformat(),
        },
    ]

    filtered = dashboard_app._filter_hypothesis_review_rows(
        rows,
        asset="BTC",
        strategy_family="BTC_TREND_CONTINUATION",
        outcome_status="FAVORABLE",
    )

    assert len(filtered) == 1
    assert filtered[0]["asset"] == "BTC"


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
                "hypothesis_outcomes:",
                "  enabled: true",
                "  horizons_hours: [4, 24, 72]",
                "  neutral_move_pct:",
                "    BTC: 0.25",
                "    Gold: 0.20",
                "  max_lookback_days: 14",
                "hypothesis_review:",
                "  enabled: true",
                "  min_evaluated_outcomes_for_candidate: 10",
                "  min_favorable_rate_for_candidate: 0.55",
                "  max_unfavorable_rate_for_candidate: 0.40",
                "  max_avg_adverse_move_pct_for_candidate:",
                "    BTC: 1.5",
                "    Gold: 0.8",
                "  readiness_buckets:",
                "    low_below: 50",
                "    medium_below: 70",
            ]
        ),
        encoding="utf-8",
    )
