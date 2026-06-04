from __future__ import annotations

from datetime import UTC, datetime

from core.models import HypothesisReviewSummary
from paper_trading.analytics import (
    PaperAnalyticsReport,
    PaperPerformanceMetrics,
    PaperSignalReviewAnalytics,
)
from reports.paper_report import PaperTradingReportFormatter


def test_paper_report_includes_hypothesis_review_summary() -> None:
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

    output = PaperTradingReportFormatter().format(
        report,
        hypothesis_review_summary=HypothesisReviewSummary(
            total_outcomes=12,
            evaluated_outcomes=10,
            favorable_count=6,
            unfavorable_count=2,
            neutral_count=2,
            insufficient_followup_count=1,
            blocked_not_evaluated_count=1,
            favorable_rate=0.6,
            unfavorable_rate=0.2,
            neutral_rate=0.2,
            by_asset=[],
            by_strategy_family=[],
            by_regime=[],
            by_horizon=[],
            by_readiness_bucket=[],
            by_hypothesis_status=[],
            avg_move_pct=0.5,
            avg_max_favorable_move_pct=1.2,
            avg_max_adverse_move_pct=0.4,
            warnings=[],
            promoted_candidates=[{"strategy_family": "BTC_TREND_CONTINUATION", "asset": "BTC", "favorable_rate": 0.6, "evaluated_outcomes": 10}],
            blocked_candidates=[],
            candidate_progress=[],
            created_at=datetime(2026, 6, 2, tzinfo=UTC),
            lookback_days=14,
        ),
    )

    assert "Hypothesis Review Analytics:" in output
    assert "Favorable: 6 (60.00%)" in output
    assert "Review Candidates:" in output
