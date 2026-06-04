from __future__ import annotations

from core.models import (
    DailyBriefContext,
    HypothesisEdgeSliceSummary,
    HypothesisOutcome,
    HypothesisReviewSummary,
    MarketDataPoint,
    ResearchReadinessResult,
    StrategyHypothesis,
    TrendResult,
)
from scoring.models import ScoreComponent


class DailyReportFormatter:
    """Formats the Telegram-ready daily brief."""

    def format(self, brief: DailyBriefContext) -> str:
        lines = [
            "AI Trading Firm Daily Brief",
            f"Date: {brief.run_date.isoformat()}",
            f"Mode: {brief.mode.title()}",
            "Execution: Disabled (MVP Phase 1)",
            "",
            "Market Data:",
            f"BTC Price: {self._format_btc_price(brief.market_data.get('btc_price'))}",
            f"Fear & Greed Index: {self._format_fear_greed(brief.market_data.get('btc_fear_greed'))}",
            f"BTC Funding Rate: {self._format_funding_rate(brief.market_data.get('btc_funding_rate'))}",
            f"BTC Open Interest: {self._format_open_interest(brief.market_data.get('btc_open_interest'))}",
            "Gold Macro Data Status:",
            f"US10Y: {self._format_macro_value(brief.market_data.get('gold_us10y'))}",
            f"Real Yield: {self._format_macro_value(brief.market_data.get('gold_real_yield'))}",
            f"Fed Funds: {self._format_macro_value(brief.market_data.get('gold_fed_funds'))}",
            f"CPI: {self._format_macro_value(brief.market_data.get('gold_cpi'))}",
            f"DXY: {self._format_macro_value(brief.market_data.get('gold_dxy'))}",
            f"Gold Spot Price: {self._format_macro_value(brief.market_data.get('gold_spot_price'))}",
            "",
            "BTC Trend Context:",
            *self._format_trend_lines(
                brief.trend_context,
                [
                    ("btc_price", "Price"),
                    ("btc_fear_greed", "Fear & Greed"),
                    ("btc_funding_rate", "Funding Rate"),
                    ("btc_open_interest", "Open Interest"),
                ],
            ),
            "",
            "Gold Macro Trend Context:",
            *self._format_trend_lines(
                brief.trend_context,
                [
                    ("gold_us10y", "US10Y"),
                    ("gold_real_yield", "Real Yield"),
                    ("gold_fed_funds", "Fed Funds"),
                    ("gold_cpi", "CPI"),
                ],
            ),
            "",
            "Gold:",
            f"Bias: {brief.gold.bias}",
            f"Total Score: {brief.gold.total_score}/100",
            f"Confidence: {brief.gold.confidence}",
            f"Data Completeness: {brief.gold.data_completeness}%",
            "Key Reasons:",
            *self._format_list(brief.gold.reasons),
            "Score Breakdown:",
            *self._format_component_lines(brief.gold.components),
            "Warnings:",
            *self._format_list(brief.gold.warnings or ["None"]),
            "",
            "BTC:",
            f"Bias: {brief.btc.bias}",
            f"Total Score: {brief.btc.total_score}/100",
            f"Confidence: {brief.btc.confidence}",
            f"Data Completeness: {brief.btc.data_completeness}%",
            "Key Reasons:",
            *self._format_list(brief.btc.reasons),
            "Score Breakdown:",
            *self._format_component_lines(brief.btc.components),
            "Warnings:",
            *self._format_list(brief.btc.warnings or ["None"]),
            "",
            "Market Regime And Data Readiness:",
            *self._format_readiness_section(brief.research_readiness),
            "",
            "Strategy Hypotheses:",
            *self._format_strategy_hypotheses(brief.strategy_hypotheses),
            "",
            "Hypothesis Outcomes:",
            *self._format_hypothesis_outcomes(brief.hypothesis_outcomes),
            "",
            "Hypothesis Review Analytics:",
            *self._format_hypothesis_review_summary(brief.hypothesis_review_summary),
            "",
            "Hypothesis Edge Slicing:",
            *self._format_hypothesis_edge_slicing_summary(brief.hypothesis_edge_slice_summary),
            "",
            "Macro Regime:",
            brief.macro_regime,
            "",
            "Data Quality:",
            f"Overall Status: {brief.data_quality.overall_status}",
            "Source Statuses:",
            *self._format_status_map(brief.data_quality.source_statuses),
            "Notes:",
            *self._format_list(brief.data_quality.notes),
            "",
            "Risk Status:",
            f"Status: {brief.risk.status}",
            f"Data Quality: {brief.risk.data_quality}",
            f"Trade Permission: {brief.risk.trade_permission}",
            f"Daily Loss: {brief.risk.daily_loss_pct:.2f}%",
            f"Weekly Loss: {brief.risk.weekly_loss_pct:.2f}%",
            "Risk Notes:",
            *self._format_list(brief.risk.notes),
            "",
            "System Health:",
            *self._format_status_map(brief.system_health),
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_list(items: list[str]) -> list[str]:
        return [f"- {item}" for item in items]

    @staticmethod
    def _format_status_map(status_map: dict[str, str]) -> list[str]:
        return [f"{name}: {status}" for name, status in status_map.items()]

    @staticmethod
    def _format_trend_lines(
        trend_context: dict[str, TrendResult],
        ordered_keys: list[tuple[str, str]],
    ) -> list[str]:
        if not trend_context:
            return ["- Not available yet."]

        lines: list[str] = []
        for key, label in ordered_keys:
            trend = trend_context.get(key)
            if not trend:
                lines.append(f"- {label}: NOT_AVAILABLE")
                continue
            if trend.status == "OK":
                change = DailyReportFormatter._format_trend_change(trend)
                lines.append(f"- {label}: {trend.direction} ({change}). {trend.reason}")
            else:
                lines.append(f"- {label}: {trend.status}. {trend.reason}")
        return lines

    @staticmethod
    def _format_trend_change(trend: TrendResult) -> str:
        if trend.change_abs is None:
            return "change unavailable"
        if trend.change_pct is None:
            return f"{trend.change_abs:+.4f}"
        return f"{trend.change_abs:+.4f}, {trend.change_pct:+.2f}%"

    @staticmethod
    def _format_component_lines(components: list[ScoreComponent]) -> list[str]:
        if not components:
            return ["- None"]

        lines: list[str] = []
        for component in components:
            contribution = f"{component.score_contribution:+d}"
            raw_suffix = DailyReportFormatter._format_component_raw_value(component)
            lines.append(f"- {component.name}: {contribution}/{component.max_score} ({component.status}){raw_suffix}")
        return lines

    @staticmethod
    def _format_readiness_section(
        readiness_by_asset: dict[str, ResearchReadinessResult],
    ) -> list[str]:
        if not readiness_by_asset:
            return ["- Not available yet."]

        lines: list[str] = []
        for asset in ("BTC", "Gold"):
            readiness = readiness_by_asset.get(asset)
            if readiness is None:
                lines.append(f"{asset}: NOT_AVAILABLE")
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
        return lines

    @staticmethod
    def _format_strategy_hypotheses(
        hypotheses_by_asset: dict[str, StrategyHypothesis],
    ) -> list[str]:
        if not hypotheses_by_asset:
            return ["- Not available yet."]

        lines: list[str] = []
        for asset in ("BTC", "Gold"):
            hypothesis = hypotheses_by_asset.get(asset)
            if hypothesis is None:
                lines.append(f"{asset}: NOT_AVAILABLE")
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
            for reason in hypothesis.reasons[:2]:
                lines.append(f"  - Reason: {reason}")
            for blocker in hypothesis.blockers[:2]:
                lines.append(f"  - Blocker: {blocker}")
            for warning in hypothesis.warnings[:2]:
                lines.append(f"  - Warning: {warning}")
        return lines

    @staticmethod
    def _format_hypothesis_outcomes(outcomes: list[HypothesisOutcome]) -> list[str]:
        if not outcomes:
            return ["- Not available yet."]

        lines: list[str] = []
        for outcome in outcomes[:6]:
            move_label = "N/A" if outcome.move_pct is None else f"{outcome.move_pct:+.2f}%"
            lines.append(
                f"- {outcome.asset} {outcome.horizon_hours}h: {outcome.outcome_status} | "
                f"Direction: {outcome.direction_bias} | Family: {outcome.strategy_family} | Move: {move_label}"
            )
            lines.append(f"  - Reason: {outcome.reason}")
            for warning in outcome.warnings[:1]:
                lines.append(f"  - Warning: {warning}")
        return lines

    @staticmethod
    def _format_hypothesis_review_summary(summary: HypothesisReviewSummary | None) -> list[str]:
        if summary is None:
            return ["- Not available yet."]

        lines = [
            (
                f"- Evaluated: {summary.evaluated_outcomes} | Favorable: {summary.favorable_count} "
                f"({summary.favorable_rate:.0%}) | Unfavorable: {summary.unfavorable_count} "
                f"({summary.unfavorable_rate:.0%}) | Neutral: {summary.neutral_count} ({summary.neutral_rate:.0%})"
            ),
            (
                f"- Insufficient Follow-Up: {summary.insufficient_followup_count} | "
                f"Blocked Not Evaluated: {summary.blocked_not_evaluated_count}"
            ),
        ]
        if summary.promoted_candidates:
            for candidate in summary.promoted_candidates[:2]:
                lines.append(
                    f"  - Review Candidate: {candidate['strategy_family']} ({candidate['asset']}) "
                    f"fav={candidate['favorable_rate']:.0%} n={candidate['evaluated_outcomes']}"
                )
        elif summary.candidate_progress:
            for candidate in summary.candidate_progress[:2]:
                lines.append(
                    f"  - Candidate Progress: {candidate['strategy_family']} ({candidate['asset']}) "
                    f"{candidate['candidate_status']} n={candidate['evaluated_outcomes']}/"
                    f"{candidate['required_min_outcomes']}"
                )
        elif summary.blocked_candidates:
            for candidate in summary.blocked_candidates[:2]:
                lines.append(
                    f"  - Blocked Candidate: {candidate['strategy_family']} ({candidate['asset']}) "
                    f"{candidate['reason']}"
                )
        for warning in summary.warnings[:2]:
            lines.append(f"  - Warning: {warning}")
        return lines

    @staticmethod
    def _format_hypothesis_edge_slicing_summary(summary: HypothesisEdgeSliceSummary | None) -> list[str]:
        if summary is None:
            return ["- Not available yet."]

        lines = [
            (
                f"- Total Slices: {summary.total_slices} | Strongest: {len(summary.strongest_slices)} | "
                f"Weakest: {len(summary.weakest_slices)} | Unstable: {len(summary.unstable_slices)}"
            ),
            "- REVIEW ONLY. No automatic promotion or trading occurs from edge slicing analytics.",
        ]
        if summary.strongest_slices:
            strongest = summary.strongest_slices[0]
            lines.append(
                f"  - Strongest: {strongest.asset} {strongest.strategy_family} {strongest.regime} "
                f"{strongest.horizon_hours}h {strongest.stability_status} fav={strongest.favorable_rate:.0%} "
                f"n={strongest.sample_size}"
            )
        if summary.weakest_slices:
            weakest = summary.weakest_slices[0]
            lines.append(
                f"  - Weakest: {weakest.asset} {weakest.strategy_family} {weakest.regime} "
                f"{weakest.horizon_hours}h {weakest.stability_status} unfav={weakest.unfavorable_rate:.0%} "
                f"n={weakest.sample_size}"
            )
        if summary.warnings:
            for warning in summary.warnings[:2]:
                lines.append(f"  - Warning: {warning}")
        return lines

    @staticmethod
    def _format_btc_price(snapshot: MarketDataPoint | None) -> str:
        if not snapshot:
            return "NOT_AVAILABLE"
        if snapshot.status == "OK" and snapshot.value:
            return f"{snapshot.value['price']:,.2f} USDT"
        return snapshot.status

    @staticmethod
    def _format_fear_greed(snapshot: MarketDataPoint | None) -> str:
        if not snapshot:
            return "NOT_AVAILABLE"
        if snapshot.status == "OK" and snapshot.value:
            value = snapshot.value["value"]
            classification = snapshot.value["classification"]
            return f"{value} ({classification})"
        return snapshot.status

    @staticmethod
    def _format_status_only(snapshot: MarketDataPoint | None) -> str:
        if not snapshot:
            return "NOT_AVAILABLE"
        return snapshot.status

    @staticmethod
    def _format_funding_rate(snapshot: MarketDataPoint | None) -> str:
        if not snapshot:
            return "NOT_AVAILABLE"
        if snapshot.status == "OK" and snapshot.value:
            funding_rate = float(snapshot.value["funding_rate"]) * 100
            return f"{funding_rate:.4f}%"
        return snapshot.status

    @staticmethod
    def _format_open_interest(snapshot: MarketDataPoint | None) -> str:
        if not snapshot:
            return "NOT_AVAILABLE"
        if snapshot.status == "OK" and snapshot.value:
            return f"{float(snapshot.value['open_interest']):,.3f}"
        return snapshot.status

    @staticmethod
    def _format_macro_value(snapshot: MarketDataPoint | None) -> str:
        if not snapshot:
            return "NOT_AVAILABLE"
        if snapshot.status == "OK" and snapshot.value:
            latest_value = snapshot.value.get("latest_value")
            timestamp_label = snapshot.value.get("observation_date") or snapshot.value.get("quote_timestamp")
            return f"{latest_value} ({timestamp_label})"
        if snapshot.status == "STALE" and snapshot.value:
            latest_value = snapshot.value.get("latest_value")
            timestamp_label = snapshot.value.get("observation_date") or snapshot.value.get("quote_timestamp")
            return f"STALE {latest_value} ({timestamp_label})"
        return snapshot.status

    @staticmethod
    def _format_component_raw_value(component: ScoreComponent) -> str:
        if isinstance(component.raw_value, dict):
            if "latest_value" in component.raw_value:
                latest_value = component.raw_value.get("latest_value")
                return f" value={latest_value}"
            if "funding_rate" in component.raw_value:
                funding_rate = float(component.raw_value.get("funding_rate", 0.0)) * 100
                return f" value={funding_rate:.4f}%"
            if "open_interest" in component.raw_value:
                open_interest = float(component.raw_value.get("open_interest", 0.0))
                return f" value={open_interest:,.3f}"
            if "price" in component.raw_value:
                return f" value={component.raw_value.get('price')}"
            if "value" in component.raw_value:
                return f" value={component.raw_value.get('value')}"
        return ""
