from __future__ import annotations

from typing import Any

from paper_trading.analytics import PaperAnalyticsReport


class PaperTradingReportFormatter:
    """Formats a local-only paper trading review report."""

    def format(self, report: PaperAnalyticsReport, paper_signal_summary: dict[str, Any] | None = None) -> str:
        performance = report.performance
        signal_review = report.signal_review
        active_profile = None
        if paper_signal_summary:
            active_profile = paper_signal_summary.get("profile")
        if not active_profile and report.latest_run_summary:
            active_profile = report.latest_run_summary.get("active_profile")

        lines = [
            "PAPER TRADING REPORT",
            "SIMULATED ONLY",
            "NO REAL EXECUTION",
            "",
            f"Database Available: {'YES' if report.database_available else 'NO'}",
            f"Message: {report.message}",
        ]

        if active_profile:
            lines.append(f"Active Paper Signal Profile: {active_profile}")

        if paper_signal_summary:
            lines.extend(
                [
                    "Signal Tuning:",
                    (
                        f"BTC thresholds: long>={paper_signal_summary.get('btc_long_score_threshold')} | "
                        f"short<={paper_signal_summary.get('btc_short_score_threshold')}"
                    ),
                    (
                        f"Gold thresholds: long>={paper_signal_summary.get('gold_long_score_threshold')} | "
                        f"short<={paper_signal_summary.get('gold_short_score_threshold')}"
                    ),
                    f"Minimum Confidence: {paper_signal_summary.get('min_confidence')}",
                    (
                        f"Minimum Data Completeness: BTC>={paper_signal_summary.get('min_btc_data_completeness')}% | "
                        f"Gold>={paper_signal_summary.get('min_gold_data_completeness')}%"
                    ),
                    f"Allow Neutral Bias: {paper_signal_summary.get('allow_neutral_bias')}",
                    f"Exploratory Mode: {paper_signal_summary.get('exploratory_mode')}",
                ]
            )

        lines.extend(
            [
                "",
                "Performance:",
                f"Starting Equity: {performance.starting_equity:,.2f}",
                f"Latest Equity: {performance.latest_equity:,.2f}",
                f"Total P&L: {performance.total_pnl_abs:,.2f}",
                f"Total P&L %: {performance.total_pnl_pct:.2f}%",
                f"Max Drawdown %: {performance.max_drawdown_pct:.2f}%",
                f"Total Orders: {performance.total_orders}",
                f"Open Positions: {performance.open_positions}",
                f"Closed Positions: {performance.closed_positions}",
                f"Total Trades: {performance.total_trades}",
                f"Winning Trades: {performance.winning_trades}",
                f"Losing Trades: {performance.losing_trades}",
                f"Win Rate: {performance.win_rate:.2f}%",
                f"Gross Profit: {performance.gross_profit:,.2f}",
                f"Gross Loss: {performance.gross_loss:,.2f}",
                f"Profit Factor: {_format_optional_float(performance.profit_factor)}",
                f"Average P&L: {performance.average_pnl:,.2f}",
                f"Average R-Multiple: {_format_optional_float(performance.average_r_multiple)}",
                "",
                "Signal Review:",
                f"Signals Evaluated: {signal_review.signals_evaluated}",
                f"Signals Accepted: {signal_review.signals_accepted}",
                f"Signals Rejected: {signal_review.signals_rejected}",
                f"No-Trade Count: {signal_review.no_trade_count}",
                f"Signal Review Source: {signal_review.source_mode}",
            ]
        )

        if signal_review.accepted_by_asset:
            lines.append("Accepted By Asset:")
            lines.extend(
                f"- {asset}: {count}"
                for asset, count in sorted(signal_review.accepted_by_asset.items())
            )

        if signal_review.rejected_by_reason:
            lines.append("Rejected By Reason:")
            lines.extend(
                f"- {reason}: {count}"
                for reason, count in sorted(signal_review.rejected_by_reason.items())
            )

        if signal_review.rejected_by_asset:
            lines.append("Rejected By Asset:")
            lines.extend(
                f"- {asset}: {count}"
                for asset, count in sorted(signal_review.rejected_by_asset.items())
            )

        if signal_review.no_trade_by_reason:
            lines.append("No-Trade By Reason:")
            lines.extend(
                f"- {reason}: {count}"
                for reason, count in sorted(signal_review.no_trade_by_reason.items())
            )

        if signal_review.no_trade_by_asset:
            lines.append("No-Trade By Asset:")
            lines.extend(
                f"- {asset}: {count}"
                for asset, count in sorted(signal_review.no_trade_by_asset.items())
            )

        if signal_review.accepted_by_profile:
            lines.append("Accepted By Profile:")
            lines.extend(
                f"- {profile}: {count}"
                for profile, count in sorted(signal_review.accepted_by_profile.items())
            )

        if signal_review.no_trade_by_profile:
            lines.append("No-Trade By Profile:")
            lines.extend(
                f"- {profile}: {count}"
                for profile, count in sorted(signal_review.no_trade_by_profile.items())
            )

        if signal_review.notes:
            lines.append("Signal Review Notes:")
            lines.extend(f"- {note}" for note in signal_review.notes)

        if report.latest_run_summary:
            lines.extend(
                [
                    "",
                    "Latest Paper Run:",
                    f"Workflow Run ID: {report.latest_run_summary.get('workflow_run_id')}",
                    f"Status: {report.latest_run_summary.get('status')}",
                    f"Run Timestamp: {report.latest_run_summary.get('run_timestamp')}",
                    f"Active Profile: {report.latest_run_summary.get('active_profile')}",
                    f"Signals Evaluated: {report.latest_run_summary.get('signals_evaluated')}",
                    f"Signals Accepted: {report.latest_run_summary.get('signals_accepted')}",
                    f"Signals Rejected: {report.latest_run_summary.get('signals_rejected')}",
                    f"No-Trade Count: {report.latest_run_summary.get('no_trade_count')}",
                    f"Orders Opened: {report.latest_run_summary.get('orders_opened')}",
                    f"Positions Updated: {report.latest_run_summary.get('positions_updated')}",
                    f"Equity Snapshot ID: {report.latest_run_summary.get('equity_snapshot_id')}",
                ]
            )
            notes = report.latest_run_summary.get("notes", [])
            if isinstance(notes, list) and notes:
                lines.append("Run Notes:")
                lines.extend(f"- {note}" for note in notes)

        return "\n".join(lines)


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"
