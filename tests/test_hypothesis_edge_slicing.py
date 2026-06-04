from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from analytics.hypothesis_edge_slicing import HypothesisEdgeSlicingAnalyzer
from core.config import (
    HypothesisEdgeSlicingConfig,
    HypothesisReviewBucketsConfig,
)
from database.init_db import initialize_database


def test_empty_outcomes_returns_safe_summary(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    summary = _build_analyzer(database_path).build_summary(now=datetime(2026, 6, 4, tzinfo=UTC))

    assert summary.total_slices == 0
    assert summary.slice_rows == []
    assert summary.warnings


def test_sample_size_below_threshold_is_insufficient_sample(tmp_path: Path) -> None:
    summary = _build_summary_with_rows(
        tmp_path,
        [
            _outcome_row(status="FAVORABLE", asset="BTC", strategy_family="BTC_TREND_CONTINUATION", regime="TREND_UP", readiness_score=80, confidence="Medium")
            for _ in range(3)
        ],
    )

    assert summary.total_slices == 1
    assert summary.slice_rows[0].stability_status == "INSUFFICIENT_SAMPLE"
    assert summary.slice_rows[0].candidate_status == "NEED_MORE_SAMPLES"


def test_strong_favorable_slice_is_strong_positive(tmp_path: Path) -> None:
    rows = [
        _outcome_row(status="FAVORABLE", asset="BTC", strategy_family="BTC_TREND_CONTINUATION", regime="TREND_UP", readiness_score=84, confidence="High")
        for _ in range(7)
    ]
    rows.extend(
        [
            _outcome_row(status="UNFAVORABLE", asset="BTC", strategy_family="BTC_TREND_CONTINUATION", regime="TREND_UP", readiness_score=84, confidence="High"),
            _outcome_row(status="NEUTRAL", asset="BTC", strategy_family="BTC_TREND_CONTINUATION", regime="TREND_UP", readiness_score=84, confidence="High"),
            _outcome_row(status="NEUTRAL", asset="BTC", strategy_family="BTC_TREND_CONTINUATION", regime="TREND_UP", readiness_score=84, confidence="High"),
        ]
    )

    summary = _build_summary_with_rows(tmp_path, rows)

    assert summary.slice_rows[0].stability_status == "STRONG_POSITIVE"
    assert summary.slice_rows[0].candidate_status == "REVIEW_CANDIDATE"
    assert summary.strongest_slices[0].strategy_family == "BTC_TREND_CONTINUATION"


def test_high_unfavorable_rate_is_negative(tmp_path: Path) -> None:
    rows = [
        _outcome_row(status="UNFAVORABLE", asset="BTC", strategy_family="BTC_DERIVATIVES_CONFIRMATION", regime="RANGE", readiness_score=72, confidence="Medium")
        for _ in range(5)
    ]
    rows.extend(
        [
            _outcome_row(status="FAVORABLE", asset="BTC", strategy_family="BTC_DERIVATIVES_CONFIRMATION", regime="RANGE", readiness_score=72, confidence="Medium")
            for _ in range(3)
        ]
    )
    rows.extend(
        [
            _outcome_row(status="NEUTRAL", asset="BTC", strategy_family="BTC_DERIVATIVES_CONFIRMATION", regime="RANGE", readiness_score=72, confidence="Medium")
            for _ in range(2)
        ]
    )

    summary = _build_summary_with_rows(tmp_path, rows)

    assert summary.slice_rows[0].stability_status == "NEGATIVE"
    assert summary.weakest_slices[0].strategy_family == "BTC_DERIVATIVES_CONFIRMATION"


def test_high_adverse_move_is_high_adverse_move(tmp_path: Path) -> None:
    summary = _build_summary_with_rows(
        tmp_path,
        [
            _outcome_row(
                status="FAVORABLE",
                asset="BTC",
                strategy_family="BTC_SENTIMENT_MEAN_REVERSION",
                regime="RANGE",
                readiness_score=75,
                confidence="Medium",
                max_adverse_move_pct=2.2,
            )
            for _ in range(10)
        ],
    )

    assert summary.slice_rows[0].stability_status == "HIGH_ADVERSE_MOVE"


def test_grouping_and_bucket_classification_work(tmp_path: Path) -> None:
    created_at = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    summary = _build_summary_with_rows(
        tmp_path,
        [
            _outcome_row(
                status="FAVORABLE",
                asset="BTC",
                strategy_family="BTC_TREND_CONTINUATION",
                regime="TREND_UP",
                readiness_score=85,
                confidence="High",
                horizon_hours=4,
                created_at=created_at,
            ),
            _outcome_row(
                status="NEUTRAL",
                asset="Gold",
                strategy_family="GOLD_MACRO_PRESSURE",
                regime="MIXED",
                readiness_score=65,
                confidence="Medium",
                horizon_hours=24,
                created_at=created_at,
            ),
            _outcome_row(
                status="UNFAVORABLE",
                asset="Gold",
                strategy_family="GOLD_USD_DXY_CONFIRMATION",
                regime="MACRO_BEARISH",
                readiness_score=40,
                confidence="Low",
                horizon_hours=72,
                created_at=created_at,
            ),
        ]
        + [
            _outcome_row(
                status="FAVORABLE",
                asset="Gold",
                strategy_family="GOLD_MACRO_PRESSURE",
                regime="MIXED",
                readiness_score=65,
                confidence="Medium",
                horizon_hours=24,
                created_at=created_at,
            )
            for _ in range(9)
        ]
        + [
            _outcome_row(
                status="UNFAVORABLE",
                asset="Gold",
                strategy_family="GOLD_USD_DXY_CONFIRMATION",
                regime="MACRO_BEARISH",
                readiness_score=40,
                confidence="Low",
                horizon_hours=72,
                created_at=created_at,
            )
            for _ in range(9)
        ],
    )

    keys = {
        (row.asset, row.strategy_family, row.regime, row.horizon_hours, row.readiness_bucket, row.confidence_bucket, row.weekday)
        for row in summary.slice_rows
    }

    assert ("BTC", "BTC_TREND_CONTINUATION", "TREND_UP", 4, "HIGH", "HIGH", created_at.strftime("%A").upper()) in keys
    assert ("Gold", "GOLD_MACRO_PRESSURE", "MIXED", 24, "MEDIUM", "MEDIUM", created_at.strftime("%A").upper()) in keys
    assert ("Gold", "GOLD_USD_DXY_CONFIRMATION", "MACRO_BEARISH", 72, "LOW", "LOW", created_at.strftime("%A").upper()) in keys


def _build_analyzer(database_path: Path) -> HypothesisEdgeSlicingAnalyzer:
    return HypothesisEdgeSlicingAnalyzer(
        database_path=database_path,
        config=HypothesisEdgeSlicingConfig(
            enabled=True,
            lookback_days=90,
            min_samples_per_slice=10,
            strong_favorable_rate=0.60,
            weak_favorable_rate=0.45,
            max_unfavorable_rate=0.40,
            max_avg_adverse_move_pct={"BTC": 1.5, "Gold": 0.8},
        ),
        readiness_buckets=HypothesisReviewBucketsConfig(low_below=50, medium_below=70),
    )


def _build_summary_with_rows(tmp_path: Path, rows: list[dict[str, object]]):
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-06-01', 'research', 'COMPLETED')
            """
        )
        for index, row in enumerate(rows, start=1):
            connection.execute(
                """
                INSERT INTO strategy_hypotheses (
                    id, workflow_run_id, asset, hypothesis_name, direction_bias, regime, readiness_score, score,
                    confidence, data_completeness, hypothesis_status, suggested_strategy_family,
                    suggested_holding_period, reasons_json, blockers_json, warnings_json, invalidation_notes, created_at
                )
                VALUES (?, 1, ?, ?, ?, ?, ?, 60, ?, 100, ?, ?, '1-3 days', '[]', '[]', '[]', 'Invalidate', ?)
                """,
                (
                    index,
                    row["asset"],
                    f"{row['strategy_family']} Hypothesis",
                    row["direction_bias"],
                    row["regime"],
                    row["readiness_score"],
                    row["confidence"],
                    row["hypothesis_status"],
                    row["strategy_family"],
                    row["created_at"],
                ),
            )
            connection.execute(
                """
                INSERT INTO strategy_hypothesis_outcomes (
                    hypothesis_id, workflow_run_id, asset, hypothesis_name, direction_bias, strategy_family,
                    horizon_hours, created_at, evaluated_at, entry_reference_price, followup_price, move_pct,
                    max_favorable_move_pct, max_adverse_move_pct, outcome_status, reason, warnings_json
                )
                VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, 100.0, 101.0, ?, ?, ?, ?, ?, '[]')
                """,
                (
                    index,
                    row["asset"],
                    f"{row['strategy_family']} Hypothesis",
                    row["direction_bias"],
                    row["strategy_family"],
                    row["horizon_hours"],
                    row["created_at"],
                    row["evaluated_at"],
                    row["move_pct"],
                    row["max_favorable_move_pct"],
                    row["max_adverse_move_pct"],
                    row["status"],
                    f"{row['status']} reason",
                ),
            )

    return _build_analyzer(database_path).build_summary(now=datetime(2026, 6, 4, tzinfo=UTC))


def _outcome_row(
    *,
    status: str,
    asset: str,
    strategy_family: str,
    regime: str,
    readiness_score: int,
    confidence: str,
    direction_bias: str = "LONG",
    hypothesis_status: str = "ACTIVE",
    horizon_hours: int = 24,
    move_pct: float = 1.0,
    max_favorable_move_pct: float = 1.2,
    max_adverse_move_pct: float = 0.4,
    created_at: datetime | None = None,
) -> dict[str, object]:
    created = created_at or datetime(2026, 6, 1, tzinfo=UTC)
    return {
        "status": status,
        "asset": asset,
        "strategy_family": strategy_family,
        "regime": regime,
        "readiness_score": readiness_score,
        "confidence": confidence,
        "direction_bias": direction_bias,
        "hypothesis_status": hypothesis_status,
        "horizon_hours": horizon_hours,
        "move_pct": move_pct,
        "max_favorable_move_pct": max_favorable_move_pct,
        "max_adverse_move_pct": max_adverse_move_pct,
        "created_at": created.isoformat(),
        "evaluated_at": datetime(2026, 6, 2, tzinfo=UTC).isoformat(),
    }
