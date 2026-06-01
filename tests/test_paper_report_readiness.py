from __future__ import annotations

from core.models import ResearchReadinessResult
from paper_trading.analytics import (
    PaperAnalyticsReport,
    PaperPerformanceMetrics,
    PaperSignalReviewAnalytics,
)
from reports.paper_report import PaperTradingReportFormatter


def test_paper_report_includes_research_readiness_summary() -> None:
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
        research_readiness={
            "BTC": ResearchReadinessResult(
                asset="BTC",
                readiness_score=78,
                regime="RANGE",
                data_completeness=100,
                stale_sources=[],
                missing_sources=[],
                warnings=[],
                decision_ready=True,
                no_trade_reasons=[],
            ),
            "Gold": ResearchReadinessResult(
                asset="Gold",
                readiness_score=35,
                regime="INSUFFICIENT_DATA",
                data_completeness=35,
                stale_sources=["Gold CPI"],
                missing_sources=["Gold DXY"],
                warnings=[],
                decision_ready=False,
                no_trade_reasons=["Readiness score 35 is below the configured minimum 70."],
            ),
        },
    )

    assert "Market Regime And Data Readiness:" in output
    assert "Regime: RANGE | Readiness Score: 78/100 | Decision Ready: YES" in output
    assert "Regime: INSUFFICIENT_DATA | Readiness Score: 35/100 | Decision Ready: NO" in output
    assert "Readiness score 35 is below the configured minimum 70." in output
