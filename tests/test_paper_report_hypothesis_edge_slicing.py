from __future__ import annotations

from datetime import UTC, datetime

from core.models import HypothesisEdgeSliceRow, HypothesisEdgeSliceSummary
from paper_trading.analytics import (
    PaperAnalyticsReport,
    PaperPerformanceMetrics,
    PaperSignalReviewAnalytics,
)
from reports.paper_report import PaperTradingReportFormatter


def test_paper_report_includes_hypothesis_edge_slicing_summary() -> None:
    report = PaperAnalyticsReport(
        database_available=True,
        message="Loaded paper analytics from local SQLite.",
        performance=PaperPerformanceMetrics(
            starting_equity=10_000.0,
            latest_equity=10_000.0,
            total_pnl_abs=0.0,
            total_pnl_pct=0.0,
            max_drawdown_pct=0.0,
            total_orders=0,
            open_positions=0,
            closed_positions=0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            gross_profit=0.0,
            gross_loss=0.0,
            profit_factor=None,
            average_pnl=0.0,
            average_r_multiple=None,
        ),
        signal_review=PaperSignalReviewAnalytics(
            signals_evaluated=0,
            signals_accepted=0,
            signals_rejected=0,
            no_trade_count=0,
        ),
    )
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
        warnings=[],
    )

    output = PaperTradingReportFormatter().format(
        report,
        hypothesis_edge_slice_summary=HypothesisEdgeSliceSummary(
            total_slices=3,
            generated_at=datetime(2026, 6, 4, tzinfo=UTC),
            lookback_days=90,
            slice_rows=[row],
            warnings=["2 slices remain below the minimum sample size of 10."],
            strongest_slices=[row],
            weakest_slices=[],
            unstable_slices=[],
        ),
    )

    assert "Hypothesis Edge Slicing:" in output
    assert "Strongest Slice:" in output
    assert "BTC_TREND_CONTINUATION" in output
