from __future__ import annotations

from paper_trading.analytics import (
    PaperAnalyticsReport,
    PaperPerformanceMetrics,
    PaperSignalReviewAnalytics,
)
from reports.paper_report import PaperTradingReportFormatter


def test_paper_report_formatter_labels_simulated_only_output() -> None:
    report = PaperAnalyticsReport(
        database_available=True,
        message="Loaded paper analytics from local SQLite.",
        performance=PaperPerformanceMetrics(
            starting_equity=10_000.0,
            latest_equity=10_050.0,
            total_pnl_abs=50.0,
            total_pnl_pct=0.5,
            max_drawdown_pct=1.75,
            total_orders=3,
            open_positions=1,
            closed_positions=2,
            total_trades=2,
            winning_trades=1,
            losing_trades=1,
            win_rate=50.0,
            gross_profit=40.0,
            gross_loss=25.0,
            profit_factor=1.6,
            average_pnl=7.5,
            average_r_multiple=0.75,
        ),
        signal_review=PaperSignalReviewAnalytics(
            signals_evaluated=4,
            signals_accepted=1,
            signals_rejected=2,
            no_trade_count=1,
            rejected_by_reason={"Signal risk exceeds max_risk_per_trade_pct.": 1},
            rejected_by_asset={"BTC": 1},
        ),
        latest_run_summary={
            "workflow_run_id": 7,
            "status": "COMPLETED",
            "run_timestamp": "2026-06-01T02:00:00+00:00",
            "signals_evaluated": 4,
            "signals_accepted": 1,
            "signals_rejected": 2,
            "no_trade_count": 1,
            "orders_opened": 1,
            "positions_updated": 1,
            "equity_snapshot_id": 3,
            "notes": ["Simulated only."],
        },
    )

    output = PaperTradingReportFormatter().format(report)

    assert "PAPER TRADING REPORT" in output
    assert "SIMULATED ONLY" in output
    assert "NO REAL EXECUTION" in output
    assert "Profit Factor: 1.60" in output
    assert "Latest Paper Run:" in output
    assert "Workflow Run ID: 7" in output
    assert "Run Notes:" in output
    assert "- Simulated only." in output
