from __future__ import annotations

from paper_trading.analytics import (
    PaperAnalyticsReport,
    PaperPerformanceMetrics,
    PaperSignalReviewAnalytics,
)
from reports.paper_report import PaperTradingReportFormatter


def test_paper_report_includes_signal_tuning_and_normalized_review_sections() -> None:
    report = PaperAnalyticsReport(
        database_available=True,
        message="Loaded paper analytics from local SQLite.",
        performance=PaperPerformanceMetrics(
            starting_equity=10_000.0,
            latest_equity=10_010.0,
            total_pnl_abs=10.0,
            total_pnl_pct=0.1,
            max_drawdown_pct=0.5,
            total_orders=1,
            open_positions=0,
            closed_positions=1,
            total_trades=1,
            winning_trades=1,
            losing_trades=0,
            win_rate=100.0,
            gross_profit=10.0,
            gross_loss=0.0,
            profit_factor=None,
            average_pnl=10.0,
            average_r_multiple=0.5,
        ),
        signal_review=PaperSignalReviewAnalytics(
            signals_evaluated=2,
            signals_accepted=1,
            signals_rejected=0,
            no_trade_count=1,
            accepted_by_asset={"BTC": 1},
            no_trade_by_asset={"Gold": 1},
            no_trade_by_reason={"CONFIDENCE_TOO_LOW": 1},
            accepted_by_profile={"balanced": 1},
            no_trade_by_profile={"balanced": 1},
            active_profile="balanced",
            source_mode="normalized",
            notes=["Using normalized paper_signal_reviews for signal analytics (2 review rows)."],
        ),
        latest_run_summary={
            "workflow_run_id": 12,
            "status": "COMPLETED",
            "run_timestamp": "2026-06-01T02:00:00+00:00",
            "active_profile": "balanced",
            "signals_evaluated": 2,
            "signals_accepted": 1,
            "signals_rejected": 0,
            "no_trade_count": 1,
            "orders_opened": 1,
            "positions_updated": 0,
            "equity_snapshot_id": 4,
            "notes": ["Simulated only."],
        },
    )

    output = PaperTradingReportFormatter().format(
        report,
        paper_signal_summary={
            "profile": "balanced",
            "btc_long_score_threshold": 67,
            "btc_short_score_threshold": 38,
            "gold_long_score_threshold": 67,
            "gold_short_score_threshold": 38,
            "min_confidence": "Medium",
            "min_btc_data_completeness": 75,
            "min_gold_data_completeness": 55,
            "allow_neutral_bias": False,
            "exploratory_mode": False,
        },
    )

    assert "PAPER TRADING REPORT" in output
    assert "SIMULATED ONLY" in output
    assert "NO REAL EXECUTION" in output
    assert "Active Paper Signal Profile: balanced" in output
    assert "Signal Tuning:" in output
    assert "BTC thresholds: long>=67 | short<=38" in output
    assert "Signal Review Source: normalized" in output
    assert "Accepted By Asset:" in output
    assert "- BTC: 1" in output
    assert "No-Trade By Reason:" in output
    assert "- CONFIDENCE_TOO_LOW: 1" in output
    assert "No-Trade By Profile:" in output
    assert "- balanced: 1" in output
