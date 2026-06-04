from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from analytics.hypothesis_review import HypothesisReviewAnalyzer
from core.config import HypothesisReviewBucketsConfig, HypothesisReviewConfig
from database.init_db import initialize_database


def test_empty_outcomes_returns_safe_zero_summary(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    summary = HypothesisReviewAnalyzer(
        database_path=database_path,
        config=_review_config(),
        lookback_days=14,
    ).build_summary(now=datetime(2026, 6, 2, tzinfo=UTC))

    assert summary.total_outcomes == 0
    assert summary.evaluated_outcomes == 0
    assert summary.favorable_rate == 0.0
    assert summary.warnings


def test_favorable_and_unfavorable_rate_calculation(tmp_path: Path) -> None:
    summary = _build_summary_with_rows(
        tmp_path,
        [
            _outcome_row(status="FAVORABLE", asset="BTC", strategy_family="BTC_TREND_CONTINUATION", regime="TREND_UP", readiness_score=85),
            _outcome_row(status="FAVORABLE", asset="BTC", strategy_family="BTC_TREND_CONTINUATION", regime="TREND_UP", readiness_score=85),
            _outcome_row(status="UNFAVORABLE", asset="BTC", strategy_family="BTC_TREND_CONTINUATION", regime="TREND_UP", readiness_score=85),
            _outcome_row(status="NEUTRAL", asset="BTC", strategy_family="BTC_TREND_CONTINUATION", regime="TREND_UP", readiness_score=85),
        ],
    )

    assert summary.evaluated_outcomes == 4
    assert summary.favorable_rate == 0.5
    assert summary.unfavorable_rate == 0.25
    assert summary.neutral_rate == 0.25


def test_grouping_by_asset_family_regime_horizon_and_readiness_bucket(tmp_path: Path) -> None:
    summary = _build_summary_with_rows(
        tmp_path,
        [
            _outcome_row(status="FAVORABLE", asset="BTC", strategy_family="BTC_TREND_CONTINUATION", regime="TREND_UP", readiness_score=85, horizon_hours=4),
            _outcome_row(status="UNFAVORABLE", asset="Gold", strategy_family="GOLD_MACRO_PRESSURE", regime="MACRO_BEARISH", readiness_score=65, horizon_hours=24),
            _outcome_row(status="NEUTRAL", asset="Gold", strategy_family="GOLD_NO_TRADE", regime="MIXED", readiness_score=40, horizon_hours=72),
        ],
    )

    assert {row["asset"] for row in summary.by_asset} == {"BTC", "Gold"}
    assert {row["strategy_family"] for row in summary.by_strategy_family} == {
        "BTC_TREND_CONTINUATION",
        "GOLD_MACRO_PRESSURE",
        "GOLD_NO_TRADE",
    }
    assert {row["regime"] for row in summary.by_regime} == {"TREND_UP", "MACRO_BEARISH", "MIXED"}
    assert {row["horizon_hours"] for row in summary.by_horizon} == {4, 24, 72}
    assert {row["readiness_bucket"] for row in summary.by_readiness_bucket} == {"HIGH", "MEDIUM", "LOW"}


def test_promotion_candidate_requires_minimum_sample_size(tmp_path: Path) -> None:
    summary = _build_summary_with_rows(
        tmp_path,
        [
            _outcome_row(status="FAVORABLE", asset="BTC", strategy_family="BTC_TREND_CONTINUATION", regime="TREND_UP", readiness_score=85)
            for _ in range(5)
        ],
    )

    assert summary.promoted_candidates == []
    assert summary.blocked_candidates
    assert "minimum sample size" in summary.blocked_candidates[0]["reason"]
    assert summary.candidate_progress[0]["candidate_status"] == "NEED_MORE_SAMPLES"


def test_promotion_candidate_does_not_trigger_without_safe_adverse_profile(tmp_path: Path) -> None:
    rows = [
        _outcome_row(
            status="FAVORABLE",
            asset="BTC",
            strategy_family="BTC_DERIVATIVES_CONFIRMATION",
            regime="RANGE",
            readiness_score=80,
            max_adverse_move_pct=2.1,
        )
        for _ in range(10)
    ]
    summary = _build_summary_with_rows(tmp_path, rows)

    assert summary.promoted_candidates == []
    assert summary.blocked_candidates
    assert "adverse move" in summary.blocked_candidates[0]["reason"]
    assert summary.candidate_progress[0]["candidate_status"] == "FAIL_ADVERSE_MOVE"


def test_candidate_progress_can_reach_review_candidate_status(tmp_path: Path) -> None:
    rows = [
        _outcome_row(
            status="FAVORABLE",
            asset="BTC",
            strategy_family="BTC_TREND_CONTINUATION",
            regime="TREND_UP",
            readiness_score=82,
            max_adverse_move_pct=0.5,
        )
        for _ in range(10)
    ]
    summary = _build_summary_with_rows(tmp_path, rows)

    assert summary.promoted_candidates
    assert summary.candidate_progress[0]["candidate_status"] == "REVIEW_CANDIDATE"


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
                VALUES (?, 1, ?, ?, ?, ?, ?, 60, 'Medium', 100, ?, ?, '1-3 days', '[]', '[]', '[]', 'Invalidate', ?)
                """,
                (
                    index,
                    row["asset"],
                    f"{row['strategy_family']} Hypothesis",
                    row["direction_bias"],
                    row["regime"],
                    row["readiness_score"],
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

    return HypothesisReviewAnalyzer(
        database_path=database_path,
        config=_review_config(),
        lookback_days=14,
    ).build_summary(now=datetime(2026, 6, 2, tzinfo=UTC))


def _review_config() -> HypothesisReviewConfig:
    return HypothesisReviewConfig(
        enabled=True,
        min_evaluated_outcomes_for_candidate=10,
        min_favorable_rate_for_candidate=0.55,
        max_unfavorable_rate_for_candidate=0.40,
        max_avg_adverse_move_pct_for_candidate={"BTC": 1.5, "Gold": 0.8},
        readiness_buckets=HypothesisReviewBucketsConfig(low_below=50, medium_below=70),
    )


def _outcome_row(
    *,
    status: str,
    asset: str,
    strategy_family: str,
    regime: str,
    readiness_score: int,
    direction_bias: str = "LONG",
    hypothesis_status: str = "ACTIVE",
    horizon_hours: int = 24,
    move_pct: float = 1.0,
    max_favorable_move_pct: float = 1.2,
    max_adverse_move_pct: float = 0.4,
) -> dict[str, object]:
    return {
        "status": status,
        "asset": asset,
        "strategy_family": strategy_family,
        "regime": regime,
        "readiness_score": readiness_score,
        "direction_bias": direction_bias,
        "hypothesis_status": hypothesis_status,
        "horizon_hours": horizon_hours,
        "move_pct": move_pct,
        "max_favorable_move_pct": max_favorable_move_pct,
        "max_adverse_move_pct": max_adverse_move_pct,
        "created_at": datetime(2026, 6, 1, tzinfo=UTC).isoformat(),
        "evaluated_at": datetime(2026, 6, 2, tzinfo=UTC).isoformat(),
    }
