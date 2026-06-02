from __future__ import annotations

from datetime import UTC, datetime

from core.models import StrategyHypothesis
from paper_trading.analytics import (
    PaperAnalyticsReport,
    PaperPerformanceMetrics,
    PaperSignalReviewAnalytics,
)
from reports.paper_report import PaperTradingReportFormatter


def test_paper_report_includes_latest_strategy_hypotheses() -> None:
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
        strategy_hypotheses={
            "BTC": StrategyHypothesis(
                asset="BTC",
                hypothesis_name="BTC Trend Continuation Research Hypothesis",
                direction_bias="LONG",
                regime="TREND_UP",
                readiness_score=82,
                score=66,
                confidence="High",
                data_completeness=100,
                hypothesis_status="ACTIVE",
                reasons=["BTC regime is TREND_UP with strong score support."],
                blockers=[],
                warnings=[],
                suggested_strategy_family="BTC_TREND_CONTINUATION",
                suggested_holding_period="1-5 days",
                invalidation_notes="Invalidate if the regime changes.",
                created_at=datetime(2026, 6, 2, tzinfo=UTC),
            )
        },
    )

    assert "Strategy Hypotheses:" in output
    assert "Family: BTC_TREND_CONTINUATION" in output
    assert "Invalidate if the regime changes." in output
