from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from analytics.hypothesis_edge_slicing import HypothesisEdgeSlicingAnalyzer
from core.config import HypothesisEdgeSlicingConfig, HypothesisReviewBucketsConfig
from core.models import HypothesisEdgeSliceRow, HypothesisEdgeSliceSummary
from database.init_db import initialize_database
from database.repository import WorkflowRepository


def test_hypothesis_edge_slicing_summary_persistence_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    row = HypothesisEdgeSliceRow(
        slice_key="BTC|BTC_TREND_CONTINUATION|TREND_UP|24|HIGH|HIGH|MONDAY",
        asset="BTC",
        strategy_family="BTC_TREND_CONTINUATION",
        regime="TREND_UP",
        horizon_hours=24,
        readiness_bucket="HIGH",
        confidence_bucket="HIGH",
        weekday="MONDAY",
        sample_size=10,
        favorable_count=7,
        unfavorable_count=1,
        neutral_count=2,
        favorable_rate=0.7,
        unfavorable_rate=0.1,
        neutral_rate=0.2,
        avg_move_pct=0.9,
        avg_max_favorable_move_pct=1.4,
        avg_max_adverse_move_pct=0.4,
        stability_status="STRONG_POSITIVE",
        candidate_status="REVIEW_CANDIDATE",
        warnings=["Stable sample."],
    )
    summary = HypothesisEdgeSliceSummary(
        total_slices=1,
        generated_at=datetime(2026, 6, 4, tzinfo=UTC),
        lookback_days=90,
        slice_rows=[row],
        warnings=["Summary warning."],
        strongest_slices=[row],
        weakest_slices=[],
        unstable_slices=[],
    )

    WorkflowRepository(database_path).store_hypothesis_edge_slice_summary(summary)

    loaded = HypothesisEdgeSlicingAnalyzer(
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
    ).load_latest_summary()

    assert loaded is not None
    assert loaded.total_slices == 1
    assert loaded.slice_rows[0].strategy_family == "BTC_TREND_CONTINUATION"
    assert loaded.strongest_slices[0].candidate_status == "REVIEW_CANDIDATE"
