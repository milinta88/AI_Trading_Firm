from __future__ import annotations

from typing import Any

from core.models import HypothesisOutcome, HypothesisReviewSummary, ResearchReadinessResult, StrategyHypothesis
from paper_trading.analytics import PaperAnalyticsReport


class PaperTradingReportFormatter:
    """Formats a local-only paper trading review report."""

    def format(
        self,
        report: PaperAnalyticsReport,
        paper_signal_summary: dict[str, Any] | None = None,
        research_readiness: dict[str, ResearchReadinessResult] | None = None,
        strategy_hypotheses: dict[str, StrategyHypothesis] | None = None,
        hypothesis_outcomes: list[HypothesisOutcome] | None = None,
        hypothesis_review_summary: HypothesisReviewSummary | None = None,
    ) -> str:
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

        if research_readiness:
            lines.extend(
                [
                    "",
                    "Market Regime And Data Readiness:",
                    *_format_research_readiness(research_readiness),
                ]
            )

        if strategy_hypotheses:
            lines.extend(
                [
                    "",
                    "Strategy Hypotheses:",
                    *_format_strategy_hypotheses(strategy_hypotheses),
                ]
            )

        if hypothesis_outcomes:
            lines.extend(
                [
                    "",
                    "Hypothesis Outcomes:",
                    *_format_hypothesis_outcomes(hypothesis_outcomes),
                ]
            )

        if hypothesis_review_summary:
            lines.extend(
                [
                    "",
                    "Hypothesis Review Analytics:",
                    *_format_hypothesis_review_summary(hypothesis_review_summary),
                ]
            )

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


def _format_research_readiness(
    readiness_by_asset: dict[str, ResearchReadinessResult],
) -> list[str]:
    lines: list[str] = []
    for asset in ("BTC", "Gold"):
        readiness = readiness_by_asset.get(asset)
        if readiness is None:
            continue
        lines.extend(
            [
                f"{asset}:",
                (
                    f"- Regime: {readiness.regime} | Readiness Score: {readiness.readiness_score}/100 | "
                    f"Decision Ready: {'YES' if readiness.decision_ready else 'NO'}"
                ),
                f"- Data Completeness: {readiness.data_completeness}%",
                f"- Stale Sources: {', '.join(readiness.stale_sources) if readiness.stale_sources else 'None'}",
                f"- Missing Sources: {', '.join(readiness.missing_sources) if readiness.missing_sources else 'None'}",
            ]
        )
        if readiness.no_trade_reasons:
            lines.append("- No-Trade Readiness Reasons:")
            lines.extend(f"  - {reason}" for reason in readiness.no_trade_reasons)
    return lines or ["- Not available yet."]


def _format_strategy_hypotheses(
    hypotheses_by_asset: dict[str, StrategyHypothesis],
) -> list[str]:
    lines: list[str] = []
    for asset in ("BTC", "Gold"):
        hypothesis = hypotheses_by_asset.get(asset)
        if hypothesis is None:
            continue
        lines.extend(
            [
                f"{asset}:",
                (
                    f"- Status: {hypothesis.hypothesis_status} | Direction: {hypothesis.direction_bias} | "
                    f"Family: {hypothesis.suggested_strategy_family}"
                ),
                (
                    f"- Regime: {hypothesis.regime} | Readiness: {hypothesis.readiness_score}/100 | "
                    f"Score: {hypothesis.score}/100 | Confidence: {hypothesis.confidence}"
                ),
                f"- Holding Period: {hypothesis.suggested_holding_period}",
            ]
        )
        if hypothesis.reasons:
            lines.append("Reasons:")
            lines.extend(f"- {reason}" for reason in hypothesis.reasons[:3])
        if hypothesis.blockers:
            lines.append("Blockers:")
            lines.extend(f"- {blocker}" for blocker in hypothesis.blockers[:3])
        if hypothesis.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in hypothesis.warnings[:3])
        lines.append(f"Invalidation Notes: {hypothesis.invalidation_notes}")
    return lines or ["- Not available yet."]


def _format_hypothesis_outcomes(outcomes: list[HypothesisOutcome]) -> list[str]:
    lines: list[str] = []
    for outcome in outcomes[:8]:
        move_label = "N/A" if outcome.move_pct is None else f"{outcome.move_pct:+.2f}%"
        lines.extend(
            [
                f"{outcome.asset} {outcome.horizon_hours}h:",
                (
                    f"- Status: {outcome.outcome_status} | Direction: {outcome.direction_bias} | "
                    f"Family: {outcome.strategy_family} | Move: {move_label}"
                ),
                f"- Reason: {outcome.reason}",
            ]
        )
        if outcome.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in outcome.warnings[:2])
    return lines or ["- Not available yet."]


def _format_hypothesis_review_summary(summary: HypothesisReviewSummary) -> list[str]:
    lines = [
        f"Total Outcomes: {summary.total_outcomes}",
        f"Evaluated Outcomes: {summary.evaluated_outcomes}",
        f"Favorable: {summary.favorable_count} ({summary.favorable_rate:.2%})",
        f"Unfavorable: {summary.unfavorable_count} ({summary.unfavorable_rate:.2%})",
        f"Neutral: {summary.neutral_count} ({summary.neutral_rate:.2%})",
        f"Insufficient Follow-Up Data: {summary.insufficient_followup_count}",
        f"Blocked Not Evaluated: {summary.blocked_not_evaluated_count}",
    ]
    if summary.promoted_candidates:
        lines.append("Review Candidates:")
        lines.extend(
            f"- {candidate['strategy_family']} | Asset {candidate['asset']} | Favorable {candidate['favorable_rate']:.2%} | Evaluated {candidate['evaluated_outcomes']}"
            for candidate in summary.promoted_candidates[:5]
        )
    if summary.blocked_candidates:
        lines.append("Blocked Candidates:")
        lines.extend(
            f"- {candidate['strategy_family']} | {candidate['reason']}"
            for candidate in summary.blocked_candidates[:5]
        )
    if summary.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in summary.warnings[:5])
    return lines
