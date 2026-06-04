from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import dashboard.app as dashboard_app
from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loader_handles_missing_edge_slicing_tables(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("DROP TABLE hypothesis_edge_slice_rows")
        connection.execute("DROP TABLE hypothesis_edge_slice_summaries")

    data = load_dashboard_data(tmp_path)

    assert data.hypothesis_edge_slicing_enabled is True
    assert data.latest_hypothesis_edge_slice_summary is not None
    assert data.latest_hypothesis_edge_slice_summary["total_slices"] == 0
    assert data.hypothesis_edge_slice_rows == []


def test_dashboard_loader_reads_latest_edge_summary_and_slice_rows(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    strongest = [
        {
            "slice_key": "BTC|BTC_TREND_CONTINUATION|TREND_UP|24|HIGH|HIGH|MONDAY",
            "asset": "BTC",
            "strategy_family": "BTC_TREND_CONTINUATION",
            "regime": "TREND_UP",
            "horizon_hours": 24,
            "readiness_bucket": "HIGH",
            "confidence_bucket": "HIGH",
            "weekday": "MONDAY",
            "sample_size": 10,
            "favorable_count": 7,
            "unfavorable_count": 1,
            "neutral_count": 2,
            "favorable_rate": 0.7,
            "unfavorable_rate": 0.1,
            "neutral_rate": 0.2,
            "avg_move_pct": 0.9,
            "avg_max_favorable_move_pct": 1.4,
            "avg_max_adverse_move_pct": 0.4,
            "stability_status": "STRONG_POSITIVE",
            "candidate_status": "REVIEW_CANDIDATE",
            "warnings": [],
        }
    ]

    with closing(sqlite3.connect(database_path)) as connection, connection:
        cursor = connection.execute(
            """
            INSERT INTO hypothesis_edge_slice_summaries (
                created_at, lookback_days, total_slices,
                strongest_slices_json, weakest_slices_json, unstable_slices_json, warnings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime(2026, 6, 4, tzinfo=UTC).isoformat(),
                90,
                1,
                json.dumps(strongest),
                json.dumps([]),
                json.dumps([]),
                json.dumps([]),
            ),
        )
        summary_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO hypothesis_edge_slice_rows (
                summary_id, slice_key, asset, strategy_family, regime, horizon_hours,
                readiness_bucket, confidence_bucket, weekday, sample_size,
                favorable_count, unfavorable_count, neutral_count,
                favorable_rate, unfavorable_rate, neutral_rate,
                avg_move_pct, avg_max_favorable_move_pct, avg_max_adverse_move_pct,
                stability_status, candidate_status, warnings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary_id,
                strongest[0]["slice_key"],
                strongest[0]["asset"],
                strongest[0]["strategy_family"],
                strongest[0]["regime"],
                strongest[0]["horizon_hours"],
                strongest[0]["readiness_bucket"],
                strongest[0]["confidence_bucket"],
                strongest[0]["weekday"],
                strongest[0]["sample_size"],
                strongest[0]["favorable_count"],
                strongest[0]["unfavorable_count"],
                strongest[0]["neutral_count"],
                strongest[0]["favorable_rate"],
                strongest[0]["unfavorable_rate"],
                strongest[0]["neutral_rate"],
                strongest[0]["avg_move_pct"],
                strongest[0]["avg_max_favorable_move_pct"],
                strongest[0]["avg_max_adverse_move_pct"],
                strongest[0]["stability_status"],
                strongest[0]["candidate_status"],
                json.dumps([]),
            ),
        )

    data = load_dashboard_data(tmp_path)

    assert data.latest_hypothesis_edge_slice_summary is not None
    assert data.latest_hypothesis_edge_slice_summary["strongest_slices"][0]["strategy_family"] == "BTC_TREND_CONTINUATION"
    assert data.hypothesis_edge_slice_rows[0]["stability_status"] == "STRONG_POSITIVE"


def test_edge_filters_handle_empty_rows() -> None:
    assert dashboard_app._filter_hypothesis_edge_rows([], asset="BTC", confidence_bucket="HIGH") == []


def test_edge_filters_can_drill_down_by_confidence_and_weekday() -> None:
    rows = [
        {
            "asset": "BTC",
            "strategy_family": "BTC_TREND_CONTINUATION",
            "regime": "TREND_UP",
            "horizon_hours": 24,
            "readiness_bucket": "HIGH",
            "confidence_bucket": "HIGH",
            "weekday": "MONDAY",
            "stability_status": "STRONG_POSITIVE",
        },
        {
            "asset": "Gold",
            "strategy_family": "GOLD_MACRO_PRESSURE",
            "regime": "MIXED",
            "horizon_hours": 24,
            "readiness_bucket": "MEDIUM",
            "confidence_bucket": "MEDIUM",
            "weekday": "TUESDAY",
            "stability_status": "NEUTRAL",
        },
    ]

    filtered = dashboard_app._filter_hypothesis_edge_rows(
        rows,
        confidence_bucket="HIGH",
        weekday="MONDAY",
        stability_status="STRONG_POSITIVE",
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
                "hypothesis_edge_slicing:",
                "  enabled: true",
                "  lookback_days: 90",
                "  min_samples_per_slice: 10",
                "  strong_favorable_rate: 0.60",
                "  weak_favorable_rate: 0.45",
                "  max_unfavorable_rate: 0.40",
                "  max_avg_adverse_move_pct:",
                "    BTC: 1.5",
                "    Gold: 0.8",
            ]
        ),
        encoding="utf-8",
    )
