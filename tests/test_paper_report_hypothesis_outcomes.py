from __future__ import annotations

from datetime import UTC, datetime

from core.models import HypothesisOutcome
from paper_trading.analytics import (
    PaperAnalyticsReport,
    PaperPerformanceMetrics,
    PaperSignalReviewAnalytics,
)
from reports.paper_report import PaperTradingReportFormatter


def test_paper_report_includes_hypothesis_outcomes() -> None:
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
        hypothesis_outcomes=[
            HypothesisOutcome(
                hypothesis_id=1,
                workflow_run_id=1,
                asset="BTC",
                hypothesis_name="BTC Trend Continuation Research Hypothesis",
                direction_bias="LONG",
                strategy_family="BTC_TREND_CONTINUATION",
                horizon_hours=24,
                created_at=datetime(2026, 6, 1, tzinfo=UTC),
                evaluated_at=datetime(2026, 6, 2, tzinfo=UTC),
                entry_reference_price=100.0,
                followup_price=101.0,
                move_pct=1.0,
                max_favorable_move_pct=1.5,
                max_adverse_move_pct=0.3,
                outcome_status="FAVORABLE",
                reason="LONG hypothesis moved favorably.",
                warnings=[],
            )
        ],
    )

    assert "Hypothesis Outcomes:" in output
    assert "BTC 24h:" in output
    assert "FAVORABLE" in output
