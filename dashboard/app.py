from __future__ import annotations

from dataclasses import MISSING, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import streamlit as st

from analytics.hypothesis_review import summarize_hypothesis_review_rows
from analytics.hypothesis_review_export import (
    HYPOTHESIS_REVIEW_NOTE_HEADERS,
    HYPOTHESIS_REVIEW_SUMMARY_HEADERS,
    HypothesisReviewExportService,
)
from core.config import HypothesisEdgeSlicingConfig, HypothesisReviewBucketsConfig, HypothesisReviewConfig
from database.repository import WorkflowRepository
from database.init_db import initialize_database
from dashboard.data_loader import DashboardData, filter_rows, load_dashboard_data, rows_to_csv
from paper_trading.export_service import PaperTradingExportService
from paper_trading.repository import PaperTradingRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DASHBOARD_DATA_ALIASES: dict[str, tuple[str, ...]] = {
    "app_mode": ("system_mode",),
    "latest_market_snapshots": ("market_snapshots",),
    "recent_market_snapshots": ("market_snapshots",),
    "latest_score_snapshots": ("score_snapshots",),
    "recent_score_snapshots": ("score_snapshots",),
    "trend_results": ("trend_context",),
    "latest_report_text": ("latest_daily_brief",),
    "recent_messages": ("outbound_messages",),
    "paper_signal_review_summary": ("paper_review_summary",),
    "paper_recent_signal_reviews": ("paper_signal_reviews", "paper_recent_reviews"),
    "paper_recent_run_summaries": ("paper_run_summaries",),
    "paper_analytics_summary": ("paper_performance_summary",),
    "latest_research_readiness": ("research_readiness_latest",),
    "recent_research_readiness": ("research_readiness_history",),
    "latest_strategy_hypotheses": ("strategy_hypotheses_latest",),
    "recent_strategy_hypotheses": ("strategy_hypotheses_history",),
    "latest_hypothesis_review_summary": ("hypothesis_review_summary",),
    "recent_hypothesis_review_summaries": ("hypothesis_review_history",),
    "latest_hypothesis_edge_slice_summary": ("hypothesis_edge_slice_summary",),
    "recent_hypothesis_edge_slice_summaries": ("hypothesis_edge_slice_history",),
    "hypothesis_edge_slice_rows": ("hypothesis_edge_slices",),
}


def main() -> None:
    st.set_page_config(
        page_title="AI Trading Firm Dashboard",
        page_icon=":bar_chart:",
        layout="wide",
    )

    limit_rows = st.sidebar.slider("Limit rows", min_value=10, max_value=500, value=100, step=10)
    data = _coerce_dashboard_data(load_dashboard_data(PROJECT_ROOT, limit=limit_rows))
    filters = _render_sidebar_filters(data, limit_rows)

    st.title("AI Trading Firm Dashboard")
    st.caption("Research monitoring only. No real trading. Watch Only.")
    st.warning("Safety: No real trading, no order routing, no MT5 order sending, no private exchange execution.")

    _render_status_header(data)

    if not data.database_available:
        st.info(data.database_message)
        _render_safety_view(data)
        return

    tabs = st.tabs(
        [
            "Overview",
            "Market Snapshots",
            "Trend Context",
            "Research Readiness",
            "Strategy Hypotheses",
            "Score Snapshots",
            "Daily Brief",
            "Report Archive",
            "Data Hygiene",
            "Paper Trading",
            "Safety And Risk",
        ]
    )

    with tabs[0]:
        _render_overview(data)
    with tabs[1]:
        _render_market_snapshots(data, filters)
    with tabs[2]:
        _render_trend_context(data, filters)
    with tabs[3]:
        _render_research_readiness(data)
    with tabs[4]:
        _render_strategy_hypotheses(data, filters)
    with tabs[5]:
        _render_score_snapshots(data, filters)
    with tabs[6]:
        _render_daily_brief(data)
    with tabs[7]:
        _render_report_archive(data)
    with tabs[8]:
        _render_data_hygiene(data)
    with tabs[9]:
        _render_paper_trading(data)
    with tabs[10]:
        _render_safety_view(data)


def _render_sidebar_filters(data: DashboardData, limit_rows: int) -> dict[str, Any]:
    data = _coerce_dashboard_data(data)
    st.sidebar.header("Filters")
    st.sidebar.caption("Filters affect dashboard tables, charts, and CSV exports only.")

    assets = sorted(
        {
            str(row.get("asset"))
            for row in data.recent_market_snapshots + data.recent_score_snapshots
            if row.get("asset")
        }
    )
    data_types = sorted(
        {
            str(row.get("data_type"))
            for row in data.recent_market_snapshots
            if row.get("data_type")
        }
    )

    asset = st.sidebar.selectbox("Asset", ["All", *assets])
    data_type = st.sidebar.selectbox("Data type", ["All", *data_types])
    start_date, end_date = _render_date_filter(data)

    return {
        "asset": None if asset == "All" else asset,
        "data_type": None if data_type == "All" else data_type,
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit_rows,
    }


def _render_date_filter(data: DashboardData) -> tuple[date | None, date | None]:
    available_dates = [
        row_date
        for row in data.recent_market_snapshots + data.recent_score_snapshots
        if (row_date := _coerce_date(row.get("timestamp"))) is not None
    ]
    if not available_dates:
        st.sidebar.info("No snapshot dates available yet.")
        return None, None

    min_date = min(available_dates)
    max_date = max(available_dates)
    selected = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(selected, tuple):
        if len(selected) == 2:
            return selected[0], selected[1]
        if len(selected) == 1:
            return selected[0], selected[0]
    if isinstance(selected, date):
        return selected, selected
    return min_date, max_date


def _coerce_date(raw_value: Any) -> date | None:
    if isinstance(raw_value, date):
        return raw_value
    if not raw_value:
        return None
    text = str(raw_value).replace("Z", "+00:00")
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _render_status_header(data: DashboardData) -> None:
    data = _coerce_dashboard_data(data)
    status = "EXECUTION DISABLED" if not data.execution_enabled else "CONFIG ERROR: EXECUTION FLAG ENABLED"
    col_mode, col_execution, col_paper, col_database = st.columns(4)
    col_mode.metric("System Mode", data.app_mode.title())
    col_execution.metric("Execution", status)
    col_paper.metric("Paper Trading", "ENABLED" if data.paper_trading_enabled else "DISABLED")
    col_database.metric("SQLite", "OK" if data.database_available else "NOT_AVAILABLE")


def _render_overview(data: DashboardData) -> None:
    data = _coerce_dashboard_data(data)
    st.subheader("Latest Workflow Run")
    if data.latest_workflow_run:
        _render_key_value_grid(
            {
                "Run ID": data.latest_workflow_run.get("id"),
                "Run Date": data.latest_workflow_run.get("run_date"),
                "Mode": data.latest_workflow_run.get("mode"),
                "Status": data.latest_workflow_run.get("status"),
                "Completed": data.latest_workflow_run.get("completed_at"),
                "Summary": data.latest_workflow_run.get("summary"),
            }
        )
    else:
        st.info("No workflow run has been stored yet.")

    st.subheader("System Health")
    if data.system_health:
        st.dataframe(_dict_to_rows(data.system_health, "Component", "Status"), use_container_width=True)
    else:
        st.info("System health is not available yet.")

    st.subheader("Data Quality Summary")
    if data.latest_risk_snapshot:
        _render_key_value_grid(
            {
                "Risk Status": data.latest_risk_snapshot.get("status"),
                "Data Quality": data.latest_risk_snapshot.get("data_quality"),
                "Trade Permission": data.latest_risk_snapshot.get("trade_permission"),
            }
        )
        _render_text_list("Risk Notes", data.latest_risk_snapshot.get("notes", []))
    else:
        st.info("No risk or data-quality snapshot is available yet.")

    st.subheader("Recent Workflow Runs")
    _render_table(data.recent_workflow_runs, empty_message="No recent workflow runs are available.")


def _render_market_snapshots(data: DashboardData, filters: dict[str, Any]) -> None:
    data = _coerce_dashboard_data(data)
    st.subheader("Latest Market Data Snapshot")
    latest_rows = _market_rows(
        filter_rows(
            data.latest_market_snapshots,
            asset=filters.get("asset"),
            data_type=filters.get("data_type"),
        )
    )
    _render_table(latest_rows, empty_message="No market snapshots are available yet.")

    st.subheader("Market Charts")
    chart_rows = filter_rows(
        data.market_chart_rows,
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
        asset=filters.get("asset"),
        data_type=filters.get("data_type"),
        limit=filters.get("limit"),
    )
    _render_market_charts(chart_rows)

    st.subheader("Recent Market Snapshots")
    recent_rows = filter_rows(
        data.recent_market_snapshots,
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
        asset=filters.get("asset"),
        data_type=filters.get("data_type"),
        limit=filters.get("limit"),
    )
    rendered_rows = _market_rows(recent_rows)
    _render_download_button("Download market snapshots CSV", rendered_rows, "market_snapshots.csv")
    _render_table(rendered_rows, empty_message="No recent market snapshots match the selected filters.")


def _render_score_snapshots(data: DashboardData, filters: dict[str, Any]) -> None:
    data = _coerce_dashboard_data(data)
    st.subheader("Latest Score Snapshot By Asset")
    latest_score_snapshots = filter_rows(
        data.latest_score_snapshots,
        asset=filters.get("asset"),
    )
    score_rows = [
        {
            "asset": row.get("asset"),
            "total_score": row.get("total_score"),
            "bias": row.get("bias"),
            "confidence": row.get("confidence"),
            "data_completeness": row.get("data_completeness"),
            "timestamp": row.get("timestamp"),
            "warnings": "; ".join(row.get("warnings", [])) or "None",
        }
        for row in latest_score_snapshots
    ]
    _render_table(score_rows, empty_message="No score snapshots are available yet.")

    st.subheader("Asset Scores Over Time")
    score_chart_rows = filter_rows(
        data.score_chart_rows,
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
        asset=filters.get("asset"),
        limit=filters.get("limit"),
    )
    _render_score_charts(score_chart_rows)

    for row in latest_score_snapshots:
        st.markdown(f"#### {row.get('asset')} Component Breakdown")
        components = row.get("components", [])
        if components:
            _render_table(components, empty_message="No components available.")
        else:
            st.info("No components available.")
        _render_text_list("Reasons", row.get("reasons", []))
        _render_text_list("Warnings", row.get("warnings", []))

    st.subheader("Recent Score Snapshots")
    recent_score_snapshots = filter_rows(
        data.recent_score_snapshots,
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
        asset=filters.get("asset"),
        limit=filters.get("limit"),
    )
    recent_score_rows = [
        {
            "asset": row.get("asset"),
            "total_score": row.get("total_score"),
            "bias": row.get("bias"),
            "confidence": row.get("confidence"),
            "data_completeness": row.get("data_completeness"),
            "timestamp": row.get("timestamp"),
        }
        for row in recent_score_snapshots
    ]
    _render_download_button("Download score snapshots CSV", recent_score_snapshots, "score_snapshots.csv")
    _render_table(recent_score_rows, empty_message="No recent score snapshots match the selected filters.")


def _render_trend_context(data: DashboardData, filters: dict[str, Any]) -> None:
    data = _coerce_dashboard_data(data)
    st.subheader("Latest-vs-Previous Trend Context")
    if not data.trend_results:
        st.info("No trend context is available yet.")
        return

    trend_results = filter_rows(
        data.trend_results,
        asset=filters.get("asset"),
        data_type=filters.get("data_type"),
    )
    rows = [
        {
            "key": row.get("key"),
            "asset": row.get("asset"),
            "data_type": row.get("data_type"),
            "status": row.get("status"),
            "latest_value": row.get("latest_value"),
            "previous_value": row.get("previous_value"),
            "change_abs": row.get("change_abs"),
            "change_pct": row.get("change_pct"),
            "direction": row.get("direction"),
            "lookback_points": row.get("lookback_points"),
            "reason": row.get("reason"),
        }
        for row in trend_results
    ]
    _render_table(rows, empty_message="No trend context is available yet.")

    st.subheader("Multi-Point Trend Context")
    multi_point_trends = filter_rows(
        data.multi_point_trends,
        asset=filters.get("asset"),
        data_type=filters.get("data_type"),
    )
    multi_point_rows = [
        {
            "key": row.get("key"),
            "asset": row.get("asset"),
            "data_type": row.get("data_type"),
            "status": row.get("status"),
            "latest_value": row.get("latest_value"),
            "first_value": row.get("first_value"),
            "average_value": row.get("average_value"),
            "min_value": row.get("min_value"),
            "max_value": row.get("max_value"),
            "change_abs": row.get("change_abs"),
            "change_pct": row.get("change_pct"),
            "direction": row.get("direction"),
            "trend_strength": row.get("trend_strength"),
            "lookback_points": row.get("lookback_points"),
            "reason": row.get("reason"),
        }
        for row in multi_point_trends
    ]
    _render_table(multi_point_rows, empty_message="No multi-point trend context is available yet.")


def _render_daily_brief(data: DashboardData) -> None:
    data = _coerce_dashboard_data(data)
    st.subheader("Latest Generated Daily Brief")
    if data.latest_report_text:
        st.text_area("Daily Brief", data.latest_report_text, height=600)
    else:
        st.info("No stored daily brief text is available yet.")

    st.subheader("Recent Telegram / Report Logs")
    _render_table(data.recent_messages, empty_message="No outbound message logs are available yet.")


def _render_research_readiness(data: DashboardData) -> None:
    data = _coerce_dashboard_data(data)
    st.subheader("Research Readiness")
    st.caption(
        "Read-only decision-readiness foundation built from persisted market snapshots and trend history only. "
        "No execution logic is enabled."
    )

    if not getattr(data, "research_readiness_enabled", False):
        st.info("Research readiness is disabled in config.")
        return

    min_score = int(getattr(data, "research_readiness_min_score", 70) or 70)
    latest_rows = data.latest_research_readiness
    if not latest_rows:
        st.info("No research readiness data is available yet.")
        return

    readiness_by_asset = {str(row.get("asset")): row for row in latest_rows}
    btc = readiness_by_asset.get("BTC")
    gold = readiness_by_asset.get("Gold")
    if btc or gold:
        col_btc, col_gold = st.columns(2)
        _render_readiness_card(col_btc, btc, min_score)
        _render_readiness_card(col_gold, gold, min_score)

    st.markdown("#### Latest Readiness Snapshot")
    _render_table(
        _research_readiness_rows(latest_rows),
        empty_message="No latest research readiness rows are available yet.",
    )

    st.markdown("#### Readiness Details")
    for asset in ("BTC", "Gold"):
        row = readiness_by_asset.get(asset)
        if row is None:
            continue
        st.markdown(f"##### {asset}")
        _render_key_value_grid(
            {
                "Regime": row.get("regime"),
                "Readiness Score": f"{row.get('readiness_score')}/100",
                "Decision Ready": "YES" if row.get("decision_ready") else "NO",
                "Minimum Score": f"{min_score}/100",
                "Data Completeness": f"{row.get('data_completeness')}%",
            }
        )
        _render_text_list("Stale Sources", row.get("stale_sources", []))
        _render_text_list("Missing Sources", row.get("missing_sources", []))
        _render_text_list("No-Trade Readiness Reasons", row.get("no_trade_reasons", []))
        _render_text_list("Warnings", row.get("warnings", []))

    st.markdown("#### Recent Readiness History")
    _render_table(
        _research_readiness_rows(data.recent_research_readiness),
        empty_message="No persisted research readiness history is available yet.",
    )


def _render_report_archive(data: DashboardData) -> None:
    data = _coerce_dashboard_data(data)
    st.subheader("Report Archive")
    st.caption("Read-only search over persisted daily brief text and outbound message previews.")

    keyword = st.text_input("Search reports and message previews", key="archive_keyword")
    status_options = sorted({str(row.get("status")) for row in data.archive_items if row.get("status")})
    selected_status = st.selectbox("Archive status", ["All", *status_options], key="archive_status")
    start_date, end_date = _render_archive_date_filter(data.archive_items)
    filtered_items = _filter_archive_rows(data.archive_items, keyword, selected_status, start_date, end_date)
    report_items = [row for row in filtered_items if row.get("item_type") == "report"]
    message_items = [row for row in filtered_items if row.get("item_type") == "message"]

    if data.archive_latest_report:
        st.markdown("#### Latest Stored Report")
        _render_key_value_grid(
            {
                "Workflow Run": data.archive_latest_report.get("workflow_run_id"),
                "Run Date": data.archive_latest_report.get("run_date"),
                "Status": data.archive_latest_report.get("status"),
                "Completed": data.archive_latest_report.get("completed_at"),
                "Summary": data.archive_latest_report.get("summary"),
            }
        )
    else:
        st.info("No stored report text is available yet.")

    st.markdown("#### Recent Reports")
    _render_download_button("Download archive results CSV", _archive_table_rows(filtered_items), "report_archive.csv")
    _render_table(_archive_table_rows(report_items), empty_message="No reports match the selected archive filters.")

    if report_items:
        report_options = {
            f"Run {row.get('workflow_run_id')} | {row.get('run_date')} | {row.get('status')}": row
            for row in report_items
        }
        selected_label = st.selectbox("Select report preview", list(report_options.keys()), key="archive_report_select")
        selected_report = report_options[selected_label]
        report_text = str(selected_report.get("text") or "")
        st.text_area("Archived Report Text", report_text, height=500)
        st.download_button(
            label="Download selected report TXT",
            data=report_text,
            file_name=f"daily_brief_run_{selected_report.get('workflow_run_id')}.txt",
            mime="text/plain",
        )

    st.markdown("#### Recent Telegram / Message Logs")
    _render_table(_archive_table_rows(message_items), empty_message="No message logs match the selected archive filters.")


def _render_strategy_hypotheses(data: DashboardData, filters: dict[str, Any]) -> None:
    data = _coerce_dashboard_data(data)
    st.subheader("Strategy Hypotheses")
    st.caption(
        "Deterministic research hypotheses only. These are review artifacts built from scores, readiness, "
        "trend context, and data quality. They do not create orders."
    )

    if not getattr(data, "strategy_hypotheses_enabled", False):
        st.info("Strategy hypotheses are disabled in config.")
        return

    latest_rows = filter_rows(
        data.latest_strategy_hypotheses,
        asset=filters.get("asset"),
    )
    if not latest_rows:
        st.info("No strategy hypotheses are available yet.")
        return

    st.markdown("#### Latest Strategy Hypotheses")
    _render_table(
        _strategy_hypothesis_rows(latest_rows),
        empty_message="No latest strategy hypotheses are available yet.",
    )

    st.markdown("#### Strategy Details")
    for row in latest_rows:
        st.markdown(f"##### {row.get('asset')}")
        _render_key_value_grid(
            {
                "Hypothesis": row.get("hypothesis_name"),
                "Status": row.get("hypothesis_status"),
                "Direction": row.get("direction_bias"),
                "Family": row.get("suggested_strategy_family"),
                "Regime": row.get("regime"),
                "Readiness Score": f"{row.get('readiness_score')}/100",
                "Score": f"{row.get('score')}/100",
                "Confidence": row.get("confidence"),
                "Data Completeness": f"{row.get('data_completeness')}%",
                "Holding Period": row.get("suggested_holding_period"),
                "Created": row.get("created_at"),
            }
        )
        _render_text_list("Reasons", row.get("reasons", []))
        _render_text_list("Blockers", row.get("blockers", []))
        _render_text_list("Warnings", row.get("warnings", []))
        st.markdown(f"**Invalidation Notes**")
        st.write(row.get("invalidation_notes") or "None")

    st.markdown("#### Recent Strategy Hypothesis History")
    recent_rows = filter_rows(
        data.recent_strategy_hypotheses,
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
        asset=filters.get("asset"),
        limit=filters.get("limit"),
    )
    _render_table(
        _strategy_hypothesis_rows(recent_rows),
        empty_message="No recent strategy hypothesis history matches the selected filters.",
    )

    st.markdown("#### Strategy Hypothesis Outcomes")
    if not getattr(data, "hypothesis_outcomes_enabled", False):
        st.info("Hypothesis outcomes are disabled in config.")
    else:
        outcome_summary = getattr(data, "hypothesis_outcome_summary", None) or {}
        col_total, col_favorable, col_unfavorable, col_pending = st.columns(4)
        col_total.metric("Total Outcomes", outcome_summary.get("total_evaluated", 0))
        col_favorable.metric("Favorable", outcome_summary.get("favorable_count", 0))
        col_unfavorable.metric("Unfavorable", outcome_summary.get("unfavorable_count", 0))
        col_pending.metric(
            "Pending / Insufficient",
            f"{outcome_summary.get('pending_count', 0)} / {outcome_summary.get('insufficient_followup_count', 0)}",
        )

        st.markdown("#### Outcome Rate By Asset")
        _render_table(
            outcome_summary.get("by_asset", []),
            empty_message="No hypothesis outcome asset summary is available yet.",
        )

        st.markdown("#### Outcome Rate By Strategy Family")
        _render_table(
            outcome_summary.get("by_strategy_family", []),
            empty_message="No hypothesis outcome family summary is available yet.",
        )

        st.markdown("#### Latest Hypothesis Outcomes")
        latest_outcomes = filter_rows(
            getattr(data, "latest_hypothesis_outcomes", []),
            asset=filters.get("asset"),
        )
        _render_table(
            _hypothesis_outcome_rows(latest_outcomes),
            empty_message="No latest hypothesis outcomes are available yet.",
        )

        st.markdown("#### Recent Hypothesis Outcome History")
        recent_outcomes = filter_rows(
            getattr(data, "recent_hypothesis_outcomes", []),
            start_date=filters.get("start_date"),
            end_date=filters.get("end_date"),
            asset=filters.get("asset"),
            limit=filters.get("limit"),
        )
        _render_table(
            _hypothesis_outcome_rows(recent_outcomes),
            empty_message="No recent hypothesis outcome history matches the selected filters.",
        )

    st.markdown("#### Hypothesis Review Analytics")
    st.caption("REVIEW ONLY / NO TRADING")
    if not getattr(data, "hypothesis_review_enabled", False):
        st.info("Hypothesis review analytics are disabled in config.")
        return

    review_summary = getattr(data, "latest_hypothesis_review_summary", None) or {}
    review_rows = list(getattr(data, "hypothesis_review_outcomes", []))
    review_config = _coerce_hypothesis_review_config(getattr(data, "hypothesis_review_config", None))

    if not review_rows and not review_summary:
        st.info("No hypothesis review analytics are available yet.")
        return

    review_filters = _render_hypothesis_review_filters(review_rows)
    filtered_review_rows = _filter_hypothesis_review_rows(
        review_rows,
        asset=review_filters.get("asset"),
        strategy_family=review_filters.get("strategy_family"),
        regime=review_filters.get("regime"),
        horizon_hours=review_filters.get("horizon_hours"),
        outcome_status=review_filters.get("outcome_status"),
        readiness_bucket=review_filters.get("readiness_bucket"),
        hypothesis_status=review_filters.get("hypothesis_status"),
        start_date=review_filters.get("start_date"),
        end_date=review_filters.get("end_date"),
    )

    if filtered_review_rows:
        filtered_summary = asdict(
            summarize_hypothesis_review_rows(
                filtered_review_rows,
                config=review_config,
                lookback_days=int(getattr(data, "hypothesis_review_lookback_days", 14) or 14),
            )
        )
    else:
        filtered_summary = dict(review_summary)

    col_sample, col_fav, col_unfav, col_neutral, col_move, col_mae = st.columns(6)
    col_sample.metric("Sample Size", int(filtered_summary.get("evaluated_outcomes", 0)))
    col_fav.metric("Favorable", int(filtered_summary.get("favorable_count", 0)))
    col_unfav.metric("Unfavorable", int(filtered_summary.get("unfavorable_count", 0)))
    col_neutral.metric("Neutral", int(filtered_summary.get("neutral_count", 0)))
    col_move.metric("Avg Move %", _format_metric(filtered_summary.get("avg_move_pct")))
    col_mae.metric("Avg MAE %", _format_metric(filtered_summary.get("avg_max_adverse_move_pct")))

    _render_key_value_grid(
        {
            "Total Outcomes": filtered_summary.get("total_outcomes"),
            "Favorable Rate": _format_ratio(filtered_summary.get("favorable_rate")),
            "Unfavorable Rate": _format_ratio(filtered_summary.get("unfavorable_rate")),
            "Neutral Rate": _format_ratio(filtered_summary.get("neutral_rate")),
            "Insufficient Follow-Up": filtered_summary.get("insufficient_followup_count"),
            "Blocked Not Evaluated": filtered_summary.get("blocked_not_evaluated_count"),
            "Average Max Favorable Move %": filtered_summary.get("avg_max_favorable_move_pct"),
        }
    )

    _render_hypothesis_review_exports(
        data=data,
        filtered_review_rows=filtered_review_rows,
        latest_summary=review_summary,
    )

    st.markdown("#### Filtered Hypothesis Outcomes")
    _render_table(
        _hypothesis_review_outcome_rows(filtered_review_rows[: int(filters.get("limit") or len(filtered_review_rows) or 0)]),
        empty_message="No hypothesis review outcomes match the selected drilldown filters.",
    )

    st.markdown("#### By Asset")
    _render_table(
        filtered_summary.get("by_asset", []),
        empty_message="No asset-level hypothesis review analytics are available yet.",
    )

    st.markdown("#### By Strategy Family")
    _render_table(
        filtered_summary.get("by_strategy_family", []),
        empty_message="No strategy-family hypothesis review analytics are available yet.",
    )

    st.markdown("#### By Regime")
    _render_table(
        filtered_summary.get("by_regime", []),
        empty_message="No regime-level hypothesis review analytics are available yet.",
    )

    st.markdown("#### By Horizon")
    _render_table(
        filtered_summary.get("by_horizon", []),
        empty_message="No horizon-level hypothesis review analytics are available yet.",
    )

    st.markdown("#### Readiness Buckets")
    _render_table(
        filtered_summary.get("by_readiness_bucket", []),
        empty_message="No readiness-bucket analytics are available yet.",
    )

    st.markdown("#### Candidate Progress")
    _render_table(
        _candidate_progress_rows(filtered_summary.get("candidate_progress", [])),
        empty_message="No candidate progress is available yet.",
    )

    st.markdown("#### Review Candidates")
    _render_table(
        filtered_summary.get("promoted_candidates", []),
        empty_message="No review candidates have met the current thresholds yet.",
    )

    st.markdown("#### Blocked Candidates")
    _render_table(
        filtered_summary.get("blocked_candidates", []),
        empty_message="No blocked candidates are available yet.",
    )

    st.markdown("#### Review Summary History")
    _render_table(
        _hypothesis_review_summary_rows(getattr(data, "recent_hypothesis_review_summaries", [])),
        empty_message="No persisted hypothesis review summary history is available yet.",
    )

    _render_hypothesis_edge_slicing(data)
    _render_text_list("Warnings", filtered_summary.get("warnings", []))
    _render_hypothesis_review_notes(data, review_filters)


def _render_archive_date_filter(items: list[dict[str, Any]]) -> tuple[date | None, date | None]:
    available_dates = [
        row_date
        for row in items
        if (row_date := _archive_row_date(row)) is not None
    ]
    if not available_dates:
        st.info("No archive dates are available yet.")
        return None, None

    min_date = min(available_dates)
    max_date = max(available_dates)
    selected = st.date_input(
        "Archive date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="archive_date_range",
    )
    if isinstance(selected, tuple):
        if len(selected) == 2:
            return selected[0], selected[1]
        if len(selected) == 1:
            return selected[0], selected[0]
    if isinstance(selected, date):
        return selected, selected
    return min_date, max_date


def _filter_archive_rows(
    rows: list[dict[str, Any]],
    keyword: str | None,
    status: str | None,
    start_date: date | None,
    end_date: date | None,
) -> list[dict[str, Any]]:
    needle = (keyword or "").strip().lower()
    normalized_status = "" if status in {None, "", "All"} else str(status).lower()
    filtered: list[dict[str, Any]] = []

    for row in rows:
        row_date = _archive_row_date(row)
        if start_date and row_date and row_date < start_date:
            continue
        if end_date and row_date and row_date > end_date:
            continue
        if (start_date or end_date) and row_date is None:
            continue
        if normalized_status and str(row.get("status") or "").lower() != normalized_status:
            continue
        if needle and needle not in _archive_search_text(row):
            continue
        filtered.append(row)
    return filtered


def _archive_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": row.get("item_type"),
            "workflow_run_id": row.get("workflow_run_id"),
            "run_date": row.get("run_date"),
            "status": row.get("status"),
            "channel": row.get("channel"),
            "created_at": row.get("created_at"),
            "completed_at": row.get("completed_at"),
            "title": row.get("title"),
            "preview": _short_text(str(row.get("text") or ""), 220),
            "error_message": row.get("error_message"),
        }
        for row in rows
    ]


def _archive_row_date(row: dict[str, Any]) -> date | None:
    return (
        _coerce_date(row.get("run_date"))
        or _coerce_date(row.get("completed_at"))
        or _coerce_date(row.get("created_at"))
    )


def _dashboard_row_date(row: dict[str, Any]) -> date | None:
    raw_value = row.get("timestamp") or row.get("evaluated_at") or row.get("created_at") or row.get("completed_at")
    if not raw_value:
        return None
    if isinstance(raw_value, datetime):
        return raw_value.date()
    if isinstance(raw_value, date):
        return raw_value
    text = str(raw_value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _archive_search_text(row: dict[str, Any]) -> str:
    values = [
        row.get("title"),
        row.get("text"),
        row.get("summary"),
        row.get("error_message"),
        row.get("status"),
        row.get("channel"),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _short_text(value: str, max_length: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3] + "..."


def _render_data_hygiene(data: DashboardData) -> None:
    data = _coerce_dashboard_data(data)
    st.subheader("Data Hygiene")
    st.caption("Read-only checks over persisted market and score snapshots. Phase 1.9 does not delete or compact data.")

    summary = data.data_hygiene_summary
    col_market, col_score, col_status, col_warning = st.columns(4)
    col_market.metric("Market Snapshots", summary.get("total_market_snapshots", 0))
    col_score.metric("Score Snapshots", summary.get("total_score_snapshots", 0))
    col_status.metric("Overall Status", data.data_hygiene_overall_status)
    col_warning.metric("Warnings / Fails", f"{summary.get('warning_count', 0)} / {summary.get('fail_count', 0)}")

    _render_key_value_grid(
        {
            "Latest Market Snapshot": summary.get("latest_market_snapshot_timestamp"),
            "Latest Score Snapshot": summary.get("latest_score_snapshot_timestamp"),
            "Retention Policy": "Preserve all data in Phase 1.9",
            "Automatic Deletes": "Disabled",
        }
    )

    st.markdown("#### Market Status Distribution")
    _render_download_button(
        "Download hygiene status distribution CSV",
        data.data_hygiene_status_distribution,
        "data_hygiene_status_distribution.csv",
    )
    _render_table(
        data.data_hygiene_status_distribution,
        empty_message="No status distribution is available yet.",
    )

    st.markdown("#### Hygiene Checks")
    _render_download_button("Download hygiene checks CSV", data.data_hygiene_checks, "data_hygiene_checks.csv")
    _render_table(data.data_hygiene_checks, empty_message="No data hygiene checks are available yet.")


def _render_paper_trading(data: DashboardData) -> None:
    data = _coerce_dashboard_data(data)
    st.subheader("Paper Trading")
    st.error("SIMULATED ONLY - NO REAL TRADING - WATCH ONLY")
    st.caption("Paper trading reads local SQLite state only. It does not route orders or call MT5/exchange trading APIs.")

    metrics = data.paper_analytics_summary
    signal_config = getattr(data, "paper_signal_config", None) or {}
    review_summary = data.paper_signal_review_summary
    latest_equity = data.paper_latest_equity or {}
    col_enabled, col_starting, col_equity, col_pnl = st.columns(4)
    col_enabled.metric("Paper Trading", "ENABLED" if data.paper_trading_enabled else "DISABLED")
    col_starting.metric("Starting Equity", f"{metrics.get('starting_equity', 0):,.2f}")
    col_equity.metric("Latest Paper Equity", f"{metrics.get('latest_equity', latest_equity.get('equity', 0)):,.2f}")
    col_pnl.metric("Total P&L", f"{metrics.get('total_pnl_abs', 0):,.2f}")

    st.markdown("#### Paper Signal Tuning")
    _render_key_value_grid(
        {
            "Profile": signal_config.get("profile"),
            "Exploratory Mode": signal_config.get("exploratory_mode"),
            "BTC Long Threshold": signal_config.get("btc_long_score_threshold"),
            "BTC Short Threshold": signal_config.get("btc_short_score_threshold"),
            "Gold Long Threshold": signal_config.get("gold_long_score_threshold"),
            "Gold Short Threshold": signal_config.get("gold_short_score_threshold"),
            "Minimum Confidence": signal_config.get("min_confidence"),
            "Minimum BTC Data Completeness": f"{signal_config.get('min_btc_data_completeness')}%",
            "Minimum Gold Data Completeness": f"{signal_config.get('min_gold_data_completeness')}%",
            "Allow Neutral Bias": signal_config.get("allow_neutral_bias"),
        }
    )

    col_pnl_pct, col_drawdown, col_open, col_closed = st.columns(4)
    col_pnl_pct.metric("Total P&L %", f"{metrics.get('total_pnl_pct', 0):.2f}%")
    col_drawdown.metric("Max Drawdown %", f"{metrics.get('max_drawdown_pct', latest_equity.get('drawdown_pct', 0)):.2f}%")
    col_open.metric("Open Positions", metrics.get("open_positions", len(data.paper_open_positions)))
    col_closed.metric("Closed Positions", metrics.get("closed_positions", len(data.paper_closed_positions)))

    col_win_rate, col_profit_factor, col_avg_pnl, col_avg_r = st.columns(4)
    col_win_rate.metric("Win Rate", f"{metrics.get('win_rate', 0):.2f}%")
    col_profit_factor.metric("Profit Factor", _format_metric(metrics.get("profit_factor")))
    col_avg_pnl.metric("Average P&L", f"{metrics.get('average_pnl', 0):,.2f}")
    col_avg_r.metric("Average R-Multiple", _format_metric(metrics.get("average_r_multiple")))

    if data.paper_latest_run_summary:
        st.markdown("#### Latest Paper Run Summary")
        _render_key_value_grid(
            {
                "Workflow Run ID": data.paper_latest_run_summary.get("workflow_run_id"),
                "Status": data.paper_latest_run_summary.get("status"),
                "Run Timestamp": data.paper_latest_run_summary.get("run_timestamp"),
                "Active Profile": data.paper_latest_run_summary.get("active_profile"),
                "Signals Evaluated": data.paper_latest_run_summary.get("signals_evaluated"),
                "Signals Accepted": data.paper_latest_run_summary.get("signals_accepted"),
                "Signals Rejected": data.paper_latest_run_summary.get("signals_rejected"),
                "No-Trade Count": data.paper_latest_run_summary.get("no_trade_count"),
                "Orders Opened": data.paper_latest_run_summary.get("orders_opened"),
                "Positions Updated": data.paper_latest_run_summary.get("positions_updated"),
                "Equity Snapshot ID": data.paper_latest_run_summary.get("equity_snapshot_id"),
            }
        )
        _render_text_list("Run Notes", data.paper_latest_run_summary.get("notes", []))

    st.markdown("#### Paper Equity Curve")
    if data.paper_equity_curve:
        st.line_chart(data.paper_equity_curve, x="timestamp", y="equity")
    else:
        st.info("No paper equity curve has been stored yet.")

    st.markdown("#### P&L By Asset")
    if data.paper_pnl_by_asset:
        st.bar_chart(data.paper_pnl_by_asset, x="asset", y="total_pnl")
        _render_table(data.paper_pnl_by_asset, empty_message="No asset-level P&L is available yet.")
    else:
        st.info("No closed paper-trade P&L by asset is available yet.")

    st.markdown("#### Signal Review Summary")
    col_eval, col_accept, col_reject, col_no_trade = st.columns(4)
    col_eval.metric("Signals Evaluated", review_summary.get("signals_evaluated", 0))
    col_accept.metric("Accepted", review_summary.get("signals_accepted", 0))
    col_reject.metric("Rejected", review_summary.get("signals_rejected", 0))
    col_no_trade.metric("No Trade", review_summary.get("no_trade_count", 0))
    _render_key_value_grid(
        {
            "Signal Review Source": review_summary.get("source_mode", "none"),
            "Active Profile": review_summary.get("active_profile") or signal_config.get("profile"),
            "Legacy Events Ignored": review_summary.get("legacy_signal_events_ignored", 0),
        }
    )
    _render_text_list("Signal Review Notes", review_summary.get("notes", []))

    st.markdown("#### Rejection Reasons")
    if data.paper_rejection_reasons:
        st.bar_chart(data.paper_rejection_reasons, x="reason", y="rejection_count")
        _render_table(data.paper_rejection_reasons, empty_message="No rejection reasons are available.")
    else:
        st.info("No paper signal rejections have been recorded yet.")

    st.markdown("#### No-Trade Reasons")
    if data.paper_no_trade_reasons:
        st.bar_chart(data.paper_no_trade_reasons, x="reason", y="no_trade_count")
        _render_table(data.paper_no_trade_reasons, empty_message="No no-trade reasons are available.")
    else:
        st.info("No no-trade reasons have been recorded yet.")

    st.markdown("#### Normalized Signal Reviews")
    review_asset_options = sorted({str(row.get("asset")) for row in data.paper_recent_signal_reviews if row.get("asset")})
    review_profile_options = sorted({str(row.get("active_profile")) for row in data.paper_recent_signal_reviews if row.get("active_profile")})
    review_status_options = sorted({str(row.get("review_status")) for row in data.paper_recent_signal_reviews if row.get("review_status")})
    filter_asset_col, filter_profile_col, filter_status_col = st.columns(3)
    selected_review_asset = filter_asset_col.selectbox("Review Asset", ["All", *review_asset_options], key="paper_review_asset")
    selected_review_profile = filter_profile_col.selectbox("Review Profile", ["All", *review_profile_options], key="paper_review_profile")
    selected_review_status = filter_status_col.selectbox("Review Status", ["All", *review_status_options], key="paper_review_status")
    filtered_signal_reviews = _filter_signal_reviews(
        data.paper_recent_signal_reviews,
        asset=None if selected_review_asset == "All" else selected_review_asset,
        profile=None if selected_review_profile == "All" else selected_review_profile,
        review_status=None if selected_review_status == "All" else selected_review_status,
    )
    _render_table(
        _paper_signal_review_rows(filtered_signal_reviews),
        empty_message="No normalized paper signal reviews match the selected filters.",
    )

    _render_paper_review_exports(data)
    _render_paper_journal(data)

    st.markdown("#### Open Simulated Positions")
    _render_table(
        _paper_position_rows(data.paper_open_positions),
        empty_message="No open simulated positions.",
    )

    st.markdown("#### Closed Simulated Positions")
    _render_table(
        _paper_position_rows(data.paper_closed_positions),
        empty_message="No closed simulated positions are available yet.",
    )

    st.markdown("#### Recent Simulated Orders")
    _render_download_button("Download paper orders CSV", data.paper_recent_orders, "paper_orders.csv")
    _render_table(
        _paper_order_rows(data.paper_recent_orders),
        empty_message="No simulated paper orders are available.",
    )

    st.markdown("#### Recent Paper Risk Rejections / Events")
    _render_download_button("Download paper risk events CSV", data.paper_recent_risk_events, "paper_risk_events.csv")
    _render_table(
        _paper_risk_event_rows(data.paper_recent_risk_events),
        empty_message="No paper risk events are available.",
    )

    st.markdown("#### Recent Paper Run Summaries")
    _render_table(
        _paper_run_summary_rows(data.paper_recent_run_summaries),
        empty_message="No paper run summaries are available yet.",
    )


def _render_paper_review_exports(data: DashboardData) -> None:
    data = _coerce_dashboard_data(data)
    st.markdown("#### Paper Review Exports")
    st.caption("Read-only CSV exports from local SQLite paper-review data only.")

    if not data.database_path:
        st.info("Paper review exports require a local SQLite database.")
        return

    export_service = PaperTradingExportService(
        database_path=data.database_path,
        starting_equity=data.paper_trading_starting_equity,
    )
    col_reviews, col_runs, col_closed = st.columns(3)
    col_reviews.download_button(
        label="Download signal reviews CSV",
        data=export_service.export_signal_reviews_csv(),
        file_name="paper_signal_reviews.csv",
        mime="text/csv",
    )
    col_runs.download_button(
        label="Download paper run summaries CSV",
        data=export_service.export_run_summaries_csv(),
        file_name="paper_run_summaries.csv",
        mime="text/csv",
    )
    if data.paper_closed_positions:
        col_closed.download_button(
            label="Download closed paper trades CSV",
            data=export_service.export_closed_positions_csv(),
            file_name="paper_closed_positions.csv",
            mime="text/csv",
        )
    else:
        col_closed.caption("No closed simulated positions are available for CSV export yet.")


def _render_paper_journal(data: DashboardData) -> None:
    data = _coerce_dashboard_data(data)
    st.markdown("#### Paper Trade Journal")
    st.caption("Local review notes only. Adding a note does not change simulated orders, positions, or thresholds.")

    if data.database_path:
        with st.form("paper_journal_note_form", clear_on_submit=True):
            note_type = st.selectbox(
                "Note Type",
                ["GENERAL", "RUN", "SIGNAL_REVIEW", "TRADE"],
                key="paper_journal_note_type",
            )
            title = st.text_input("Title (optional)", key="paper_journal_title")
            reference_col, asset_col, profile_col = st.columns(3)
            reference_id = reference_col.text_input("Reference ID (optional)", key="paper_journal_reference_id")
            asset = asset_col.selectbox("Asset (optional)", ["", "BTC", "Gold"], key="paper_journal_asset")
            profile_options = _paper_profile_options(data)
            profile = profile_col.selectbox(
                "Profile (optional)",
                ["", *profile_options],
                key="paper_journal_profile",
            )
            tags = st.text_input("Tags (optional, comma-separated)", key="paper_journal_tags")
            note_text = st.text_area("New Journal Note", height=140, key="paper_journal_text")
            submitted = st.form_submit_button("Add Note")

        if submitted:
            if not note_text.strip():
                st.warning("Enter a journal note before saving it.")
            else:
                try:
                    initialize_database(data.database_path)
                    repository = PaperTradingRepository(data.database_path)
                    note_id = repository.add_journal_note(
                        note_type=note_type,
                        reference_id=_optional_text(reference_id),
                        asset=_optional_text(asset),
                        profile=_optional_text(profile),
                        title=_optional_text(title),
                        note_text=note_text.strip(),
                        tags=_optional_text(tags),
                    )
                except Exception:
                    st.error("Unable to save the journal note right now.")
                else:
                    if note_id:
                        st.success(f"Saved journal note #{note_id}.")
                        st.rerun()
                    else:
                        st.warning("The journal table is not available yet. Run a local workflow first and try again.")
    else:
        st.info("Paper journal notes require a local SQLite database.")

    st.markdown("#### Recent Journal Notes")
    _render_table(
        _paper_journal_rows(data.paper_journal_notes),
        empty_message="No paper journal notes are available yet.",
    )


def _render_safety_view(data: DashboardData) -> None:
    data = _coerce_dashboard_data(data)
    st.subheader("Safety And Risk")
    st.error("EXECUTION DISABLED")
    st.write("This dashboard is monitoring only. It does not place orders or change trading state.")
    _render_key_value_grid(
        {
            "risk.execution_enabled": str(data.execution_enabled),
            "paper_trading.enabled": str(data.paper_trading_enabled),
            "Trade Permission": "WATCH ONLY",
            "Real Trading": "DISABLED",
            "Order Routing": "DISABLED",
            "MT5 order_send": "NOT_CONFIGURED",
            "Private Exchange API": "NOT_CONFIGURED",
        }
    )

    if data.latest_risk_snapshot:
        st.subheader("Latest Risk Snapshot")
        _render_key_value_grid(
            {
                "Status": data.latest_risk_snapshot.get("status"),
                "Data Quality": data.latest_risk_snapshot.get("data_quality"),
                "Trade Permission": data.latest_risk_snapshot.get("trade_permission"),
                "Daily Loss %": data.latest_risk_snapshot.get("daily_loss_pct"),
                "Weekly Loss %": data.latest_risk_snapshot.get("weekly_loss_pct"),
            }
        )
        _render_text_list("Risk Notes", data.latest_risk_snapshot.get("notes", []))


def _paper_position_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "asset": row.get("asset"),
            "direction": row.get("direction"),
            "entry_price": row.get("entry_price"),
            "stop_loss": row.get("stop_loss"),
            "take_profit": row.get("take_profit"),
            "size": row.get("size"),
            "status": row.get("status"),
            "opened_at": row.get("opened_at"),
            "pnl_abs": row.get("pnl_abs"),
            "pnl_pct": row.get("pnl_pct"),
        }
        for row in rows
    ]


def _paper_order_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "created_at": row.get("created_at"),
            "asset": row.get("asset"),
            "direction": row.get("direction"),
            "order_type": row.get("order_type"),
            "status": row.get("status"),
            "signal_source": row.get("signal_source"),
            "intended_entry": row.get("intended_entry"),
            "stop_loss": row.get("stop_loss"),
            "take_profit": row.get("take_profit"),
            "risk_pct": row.get("risk_pct"),
            "size": row.get("size"),
            "warnings": "; ".join(row.get("warnings", [])) if isinstance(row.get("warnings"), list) else row.get("warnings"),
        }
        for row in rows
    ]


def _paper_risk_event_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "timestamp": row.get("timestamp"),
            "workflow_run_id": row.get("workflow_run_id"),
            "asset": row.get("asset"),
            "event_type": row.get("event_type"),
            "status": row.get("status"),
            "reason": row.get("reason"),
        }
        for row in rows
    ]


def _paper_run_summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "workflow_run_id": row.get("workflow_run_id"),
            "run_timestamp": row.get("run_timestamp"),
            "status": row.get("status"),
            "active_profile": row.get("active_profile"),
            "signals_evaluated": row.get("signals_evaluated"),
            "signals_accepted": row.get("signals_accepted"),
            "signals_rejected": row.get("signals_rejected"),
            "no_trade_count": row.get("no_trade_count"),
            "orders_opened": row.get("orders_opened"),
            "positions_updated": row.get("positions_updated"),
            "equity_snapshot_id": row.get("equity_snapshot_id"),
        }
        for row in rows
    ]


def _paper_signal_review_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "created_at": row.get("created_at"),
            "workflow_run_id": row.get("workflow_run_id"),
            "asset": row.get("asset"),
            "signal_action": row.get("signal_action"),
            "review_status": row.get("review_status"),
            "bias": row.get("bias"),
            "total_score": row.get("total_score"),
            "confidence": row.get("confidence"),
            "data_completeness": row.get("data_completeness"),
            "active_profile": row.get("active_profile"),
            "reasons": "; ".join(_review_reason_strings(row.get("reasons", []))) or "None",
            "warnings": "; ".join(row.get("warnings", [])) if isinstance(row.get("warnings"), list) else row.get("warnings"),
        }
        for row in rows
    ]


def _strategy_hypothesis_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "asset": row.get("asset"),
            "hypothesis_name": row.get("hypothesis_name"),
            "direction_bias": row.get("direction_bias"),
            "regime": row.get("regime"),
            "readiness_score": row.get("readiness_score"),
            "score": row.get("score"),
            "confidence": row.get("confidence"),
            "data_completeness": row.get("data_completeness"),
            "hypothesis_status": row.get("hypothesis_status"),
            "suggested_strategy_family": row.get("suggested_strategy_family"),
            "suggested_holding_period": row.get("suggested_holding_period"),
            "blockers": "; ".join(row.get("blockers", [])) if isinstance(row.get("blockers"), list) else row.get("blockers"),
            "warnings": "; ".join(row.get("warnings", [])) if isinstance(row.get("warnings"), list) else row.get("warnings"),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


def _hypothesis_outcome_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "asset": row.get("asset"),
            "hypothesis_name": row.get("hypothesis_name"),
            "direction_bias": row.get("direction_bias"),
            "strategy_family": row.get("strategy_family"),
            "horizon_hours": row.get("horizon_hours"),
            "outcome_status": row.get("outcome_status"),
            "move_pct": row.get("move_pct"),
            "max_favorable_move_pct": row.get("max_favorable_move_pct"),
            "max_adverse_move_pct": row.get("max_adverse_move_pct"),
            "entry_reference_price": row.get("entry_reference_price"),
            "followup_price": row.get("followup_price"),
            "reason": row.get("reason"),
            "warnings": "; ".join(row.get("warnings", [])) if isinstance(row.get("warnings"), list) else row.get("warnings"),
            "created_at": row.get("created_at"),
            "evaluated_at": row.get("evaluated_at"),
        }
        for row in rows
    ]


def _hypothesis_review_outcome_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "asset": row.get("asset"),
            "strategy_family": row.get("strategy_family"),
            "regime": row.get("regime"),
            "readiness_bucket": row.get("readiness_bucket"),
            "hypothesis_status": row.get("hypothesis_status"),
            "horizon_hours": row.get("horizon_hours"),
            "outcome_status": row.get("outcome_status"),
            "move_pct": row.get("move_pct"),
            "max_favorable_move_pct": row.get("max_favorable_move_pct"),
            "max_adverse_move_pct": row.get("max_adverse_move_pct"),
            "created_at": row.get("created_at"),
            "evaluated_at": row.get("evaluated_at"),
            "reason": row.get("reason"),
        }
        for row in rows
    ]


def _hypothesis_review_summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "created_at": row.get("created_at"),
            "lookback_days": row.get("lookback_days"),
            "total_outcomes": row.get("total_outcomes"),
            "evaluated_outcomes": row.get("evaluated_outcomes"),
            "favorable_rate": row.get("favorable_rate"),
            "unfavorable_rate": row.get("unfavorable_rate"),
            "neutral_rate": row.get("neutral_rate"),
            "review_candidates": len(row.get("promoted_candidates", [])) if isinstance(row.get("promoted_candidates"), list) else 0,
            "blocked_candidates": len(row.get("blocked_candidates", [])) if isinstance(row.get("blocked_candidates"), list) else 0,
            "warnings": "; ".join(row.get("warnings", [])) if isinstance(row.get("warnings"), list) else row.get("warnings"),
        }
        for row in rows
    ]


def _candidate_progress_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "asset": row.get("asset"),
            "strategy_family": row.get("strategy_family"),
            "candidate_status": row.get("candidate_status"),
            "evaluated_outcomes": row.get("evaluated_outcomes"),
            "required_min_outcomes": row.get("required_min_outcomes"),
            "samples_needed": row.get("samples_needed"),
            "favorable_rate": row.get("favorable_rate"),
            "required_favorable_rate": row.get("required_favorable_rate"),
            "unfavorable_rate": row.get("unfavorable_rate"),
            "max_unfavorable_rate": row.get("max_unfavorable_rate"),
            "avg_adverse_move": row.get("avg_adverse_move"),
            "max_allowed_adverse_move": row.get("max_allowed_adverse_move"),
            "reason": row.get("reason"),
        }
        for row in rows
    ]


def _research_readiness_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "asset": row.get("asset"),
            "readiness_score": row.get("readiness_score"),
            "regime": row.get("regime"),
            "data_completeness": row.get("data_completeness"),
            "decision_ready": "YES" if row.get("decision_ready") else "NO",
            "stale_sources": ", ".join(row.get("stale_sources", [])) if isinstance(row.get("stale_sources"), list) else row.get("stale_sources"),
            "missing_sources": ", ".join(row.get("missing_sources", [])) if isinstance(row.get("missing_sources"), list) else row.get("missing_sources"),
            "no_trade_reasons": "; ".join(row.get("no_trade_reasons", [])) if isinstance(row.get("no_trade_reasons"), list) else row.get("no_trade_reasons"),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


def _paper_journal_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "note_type": row.get("note_type"),
            "reference_id": row.get("reference_id"),
            "asset": row.get("asset"),
            "profile": row.get("profile"),
            "title": row.get("title"),
            "note_text": row.get("note_text"),
            "tags": row.get("tags"),
        }
        for row in rows
    ]


def _hypothesis_review_note_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": row.get("id"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "note_type": row.get("note_type"),
            "reference_type": row.get("reference_type"),
            "reference_id": row.get("reference_id"),
            "asset": row.get("asset"),
            "strategy_family": row.get("strategy_family"),
            "regime": row.get("regime"),
            "horizon_hours": row.get("horizon_hours"),
            "title": row.get("title"),
            "note_text": row.get("note_text"),
            "tags": row.get("tags"),
        }
        for row in rows
    ]


def _review_reason_strings(reasons: list[dict[str, Any]]) -> list[str]:
    rendered: list[str] = []
    for reason in reasons:
        if not isinstance(reason, dict):
            rendered.append(str(reason))
            continue
        code = str(reason.get("code", "UNKNOWN"))
        message = str(reason.get("message", "")).strip()
        rendered.append(f"{code}: {message}" if message else code)
    return rendered


def _filter_signal_reviews(
    rows: list[dict[str, Any]],
    asset: str | None = None,
    profile: str | None = None,
    review_status: str | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if asset and str(row.get("asset")) != asset:
            continue
        if profile and str(row.get("active_profile")) != profile:
            continue
        if review_status and str(row.get("review_status")) != review_status:
            continue
        filtered.append(row)
    return filtered


def _coerce_hypothesis_review_config(raw_config: Any) -> HypothesisReviewConfig:
    if isinstance(raw_config, HypothesisReviewConfig):
        return raw_config
    if isinstance(raw_config, dict):
        raw_buckets = raw_config.get("readiness_buckets", {})
        bucket_values = raw_buckets if isinstance(raw_buckets, dict) else {}
        raw_thresholds = raw_config.get("max_avg_adverse_move_pct_for_candidate", {})
        thresholds = {"BTC": 1.5, "Gold": 0.8}
        if isinstance(raw_thresholds, dict):
            for asset_key, default_value in thresholds.items():
                thresholds[asset_key] = float(raw_thresholds.get(asset_key, default_value))
        return HypothesisReviewConfig(
            enabled=bool(raw_config.get("enabled", False)),
            min_evaluated_outcomes_for_candidate=int(raw_config.get("min_evaluated_outcomes_for_candidate", 10)),
            min_favorable_rate_for_candidate=float(raw_config.get("min_favorable_rate_for_candidate", 0.55)),
            max_unfavorable_rate_for_candidate=float(raw_config.get("max_unfavorable_rate_for_candidate", 0.40)),
            max_avg_adverse_move_pct_for_candidate=thresholds,
            readiness_buckets=HypothesisReviewBucketsConfig(
                low_below=int(bucket_values.get("low_below", 50)),
                medium_below=int(bucket_values.get("medium_below", 70)),
            ),
        )
    return HypothesisReviewConfig(
        enabled=False,
        min_evaluated_outcomes_for_candidate=10,
        min_favorable_rate_for_candidate=0.55,
        max_unfavorable_rate_for_candidate=0.40,
        max_avg_adverse_move_pct_for_candidate={"BTC": 1.5, "Gold": 0.8},
        readiness_buckets=HypothesisReviewBucketsConfig(low_below=50, medium_below=70),
    )


def _render_hypothesis_review_filters(rows: list[dict[str, Any]]) -> dict[str, Any]:
    assets = sorted({str(row.get("asset")) for row in rows if row.get("asset")})
    families = sorted({str(row.get("strategy_family")) for row in rows if row.get("strategy_family")})
    regimes = sorted({str(row.get("regime")) for row in rows if row.get("regime")})
    horizons = sorted({int(row.get("horizon_hours")) for row in rows if row.get("horizon_hours") is not None})
    outcome_statuses = sorted({str(row.get("outcome_status")) for row in rows if row.get("outcome_status")})
    readiness_buckets = sorted({str(row.get("readiness_bucket")) for row in rows if row.get("readiness_bucket")})
    hypothesis_statuses = sorted({str(row.get("hypothesis_status")) for row in rows if row.get("hypothesis_status")})

    st.markdown("#### Drilldown Filters")
    filter_cols = st.columns(4)
    selected_asset = filter_cols[0].selectbox("Review Asset", ["All", *assets], key="review_asset")
    selected_family = filter_cols[1].selectbox("Strategy Family", ["All", *families], key="review_strategy_family")
    selected_regime = filter_cols[2].selectbox("Regime", ["All", *regimes], key="review_regime")
    selected_horizon = filter_cols[3].selectbox("Horizon", ["All", *horizons], key="review_horizon")

    filter_cols_2 = st.columns(3)
    selected_outcome_status = filter_cols_2[0].selectbox(
        "Outcome Status",
        ["All", *outcome_statuses],
        key="review_outcome_status",
    )
    selected_readiness_bucket = filter_cols_2[1].selectbox(
        "Readiness Bucket",
        ["All", *readiness_buckets],
        key="review_readiness_bucket",
    )
    selected_hypothesis_status = filter_cols_2[2].selectbox(
        "Hypothesis Status",
        ["All", *hypothesis_statuses],
        key="review_hypothesis_status",
    )

    start_date: date | None = None
    end_date: date | None = None
    available_dates = [row_date for row in (_row_date(row) for row in rows) if row_date is not None]
    if available_dates:
        min_date = min(available_dates)
        max_date = max(available_dates)
        selected_dates = st.date_input(
            "Review Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            key="review_date_range",
        )
        if isinstance(selected_dates, tuple):
            if len(selected_dates) == 2:
                start_date, end_date = selected_dates
            elif len(selected_dates) == 1:
                start_date = end_date = selected_dates[0]
        elif isinstance(selected_dates, date):
            start_date = end_date = selected_dates

    return {
        "asset": None if selected_asset == "All" else selected_asset,
        "strategy_family": None if selected_family == "All" else selected_family,
        "regime": None if selected_regime == "All" else selected_regime,
        "horizon_hours": None if selected_horizon == "All" else int(selected_horizon),
        "outcome_status": None if selected_outcome_status == "All" else selected_outcome_status,
        "readiness_bucket": None if selected_readiness_bucket == "All" else selected_readiness_bucket,
        "hypothesis_status": None if selected_hypothesis_status == "All" else selected_hypothesis_status,
        "start_date": start_date,
        "end_date": end_date,
    }


def _filter_hypothesis_review_rows(
    rows: list[dict[str, Any]],
    *,
    asset: str | None = None,
    strategy_family: str | None = None,
    regime: str | None = None,
    horizon_hours: int | None = None,
    outcome_status: str | None = None,
    readiness_bucket: str | None = None,
    hypothesis_status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if asset and str(row.get("asset")) != asset:
            continue
        if strategy_family and str(row.get("strategy_family")) != strategy_family:
            continue
        if regime and str(row.get("regime")) != regime:
            continue
        if horizon_hours is not None and int(row.get("horizon_hours") or 0) != int(horizon_hours):
            continue
        if outcome_status and str(row.get("outcome_status")) != outcome_status:
            continue
        if readiness_bucket and str(row.get("readiness_bucket")) != readiness_bucket:
            continue
        if hypothesis_status and str(row.get("hypothesis_status")) != hypothesis_status:
            continue
        row_date = _dashboard_row_date(row)
        if start_date and row_date and row_date < start_date:
            continue
        if end_date and row_date and row_date > end_date:
            continue
        if (start_date or end_date) and row_date is None:
            continue
        filtered.append(row)
    return filtered


def _render_hypothesis_review_exports(
    *,
    data: DashboardData,
    filtered_review_rows: list[dict[str, Any]],
    latest_summary: dict[str, Any],
) -> None:
    st.markdown("#### Review Exports")
    st.caption("Local-only CSV exports for persisted review data and currently filtered review outcomes.")

    export_service = None
    if data.database_path:
        export_service = HypothesisReviewExportService(data.database_path)

    export_cols = st.columns(3)
    export_cols[0].download_button(
        label="Download filtered hypothesis outcomes CSV",
        data=rows_to_csv(_hypothesis_review_outcome_rows(filtered_review_rows)),
        file_name="filtered_hypothesis_review_outcomes.csv",
        mime="text/csv",
    )
    export_cols[1].download_button(
        label="Download latest review summary CSV",
        data=rows_to_csv([_summary_export_row(latest_summary)], HYPOTHESIS_REVIEW_SUMMARY_HEADERS),
        file_name="latest_hypothesis_review_summary.csv",
        mime="text/csv",
    )
    notes_csv = export_service.export_review_notes_csv() if export_service else rows_to_csv([], HYPOTHESIS_REVIEW_NOTE_HEADERS)
    export_cols[2].download_button(
        label="Download notes CSV",
        data=notes_csv,
        file_name="hypothesis_review_notes.csv",
        mime="text/csv",
    )


def _render_hypothesis_review_notes(data: DashboardData, filters: dict[str, Any]) -> None:
    data = _coerce_dashboard_data(data)
    st.markdown("#### Review Tags And Notes")
    st.caption("Local review metadata only. Notes and tags do not change scores, hypotheses, paper orders, or execution state.")

    strategy_families = sorted(
        {str(row.get("strategy_family")) for row in data.hypothesis_review_outcomes if row.get("strategy_family")}
    )
    regimes = sorted({str(row.get("regime")) for row in data.hypothesis_review_outcomes if row.get("regime")})
    horizons = sorted({int(row.get("horizon_hours")) for row in data.hypothesis_review_outcomes if row.get("horizon_hours") is not None})

    if data.database_path:
        with st.form("hypothesis_review_note_form", clear_on_submit=True):
            note_type = st.selectbox(
                "Note Type",
                ["GENERAL", "OBSERVATION", "FOLLOW_UP", "CANDIDATE_REVIEW"],
                key="hypothesis_review_note_type",
            )
            reference_type = st.selectbox(
                "Reference Type",
                ["GENERAL", "HYPOTHESIS", "OUTCOME", "REVIEW_SUMMARY", "STRATEGY_FAMILY"],
                key="hypothesis_review_reference_type",
            )
            title = st.text_input("Title (optional)", key="hypothesis_review_title")
            ref_col, asset_col, family_col = st.columns(3)
            reference_id = _optional_text(ref_col.text_input("Reference ID (optional)", key="hypothesis_review_reference_id"))
            asset = asset_col.selectbox("Asset", ["", "BTC", "Gold"], key="hypothesis_review_asset")
            strategy_family = family_col.selectbox("Strategy Family", ["", *strategy_families], key="hypothesis_review_strategy_family")
            regime_col, horizon_col, tags_col = st.columns(3)
            regime = regime_col.selectbox("Regime", ["", *regimes], key="hypothesis_review_regime")
            horizon_value = horizon_col.selectbox("Horizon", ["", *horizons], key="hypothesis_review_horizon")
            tags = _optional_text(tags_col.text_input("Tags (comma-separated)", key="hypothesis_review_tags"))
            note_text = st.text_area("Review Note", key="hypothesis_review_note_text", height=120)
            submitted = st.form_submit_button("Add Review Note")
            if submitted:
                cleaned_note = note_text.strip()
                if not cleaned_note:
                    st.warning("Review note text is required.")
                else:
                    note_id = WorkflowRepository(data.database_path).add_hypothesis_review_note(
                        note_type=note_type,
                        reference_type=reference_type,
                        reference_id=reference_id,
                        asset=_optional_text(asset),
                        strategy_family=_optional_text(strategy_family),
                        regime=_optional_text(regime),
                        horizon_hours=int(horizon_value) if horizon_value not in {"", None} else None,
                        title=_optional_text(title),
                        note_text=cleaned_note,
                        tags=tags,
                    )
                    if note_id:
                        st.success(f"Saved review note #{note_id}.")
                    else:
                        st.error("Unable to save the review note to SQLite.")
    else:
        st.info("Review notes require the local SQLite database to be available.")

    filtered_notes = _filter_hypothesis_review_rows(
        data.hypothesis_review_notes,
        asset=filters.get("asset"),
        strategy_family=filters.get("strategy_family"),
        regime=filters.get("regime"),
        horizon_hours=filters.get("horizon_hours"),
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
    )
    _render_table(
        _hypothesis_review_note_rows(filtered_notes),
        empty_message="No hypothesis review notes match the selected drilldown filters.",
    )


def _render_hypothesis_edge_slicing(data: DashboardData) -> None:
    data = _coerce_dashboard_data(data)
    st.markdown("#### Hypothesis Edge Slicing")
    st.caption("REVIEW ONLY / NO TRADING")

    if not getattr(data, "hypothesis_edge_slicing_enabled", False):
        st.info("Hypothesis edge slicing is disabled in config.")
        return

    summary = getattr(data, "latest_hypothesis_edge_slice_summary", None) or {}
    slice_rows = list(getattr(data, "hypothesis_edge_slice_rows", []))
    config = _coerce_hypothesis_edge_config(getattr(data, "hypothesis_edge_slicing_config", None))

    if not summary and not slice_rows:
        st.info("No hypothesis edge slicing analytics are available yet.")
        return

    edge_filters = _render_hypothesis_edge_filters(slice_rows)
    filtered_rows = _filter_hypothesis_edge_rows(
        slice_rows,
        asset=edge_filters.get("asset"),
        strategy_family=edge_filters.get("strategy_family"),
        regime=edge_filters.get("regime"),
        horizon_hours=edge_filters.get("horizon_hours"),
        readiness_bucket=edge_filters.get("readiness_bucket"),
        confidence_bucket=edge_filters.get("confidence_bucket"),
        weekday=edge_filters.get("weekday"),
        stability_status=edge_filters.get("stability_status"),
    )

    col_total, col_strong, col_weak, col_unstable = st.columns(4)
    col_total.metric("Total Slices", len(filtered_rows) if filtered_rows else int(summary.get("total_slices", 0)))
    col_strong.metric(
        "Strong Positive",
        sum(1 for row in filtered_rows if str(row.get("stability_status")) == "STRONG_POSITIVE")
        if filtered_rows
        else len(summary.get("strongest_slices", [])),
    )
    col_weak.metric(
        "Weak / Negative",
        sum(
            1
            for row in filtered_rows
            if str(row.get("stability_status")) in {"WEAK_POSITIVE", "NEGATIVE", "HIGH_ADVERSE_MOVE"}
        )
        if filtered_rows
        else len(summary.get("weakest_slices", [])),
    )
    col_unstable.metric(
        "Sample / Unstable",
        sum(
            1
            for row in filtered_rows
            if str(row.get("stability_status")) in {"INSUFFICIENT_SAMPLE", "MIXED_OR_UNSTABLE", "NEUTRAL"}
        )
        if filtered_rows
        else len(summary.get("unstable_slices", [])),
    )

    st.download_button(
        label="Download slice rows CSV",
        data=rows_to_csv(_hypothesis_edge_slice_rows(filtered_rows or slice_rows)),
        file_name="hypothesis_edge_slice_rows.csv",
        mime="text/csv",
    )

    strongest = filtered_rows and [
        row for row in filtered_rows if str(row.get("stability_status")) in {"STRONG_POSITIVE", "WEAK_POSITIVE"}
    ] or summary.get("strongest_slices", [])
    weakest = filtered_rows and [
        row for row in filtered_rows if str(row.get("stability_status")) in {"NEGATIVE", "HIGH_ADVERSE_MOVE"}
    ] or summary.get("weakest_slices", [])
    unstable = filtered_rows and [
        row
        for row in filtered_rows
        if str(row.get("stability_status")) in {"INSUFFICIENT_SAMPLE", "MIXED_OR_UNSTABLE", "NEUTRAL"}
    ] or summary.get("unstable_slices", [])

    st.markdown("#### Strongest Slices")
    _render_table(
        _hypothesis_edge_slice_rows(strongest[:10]),
        empty_message="No strongest slices are available yet.",
    )

    st.markdown("#### Weakest Slices")
    _render_table(
        _hypothesis_edge_slice_rows(weakest[:10]),
        empty_message="No weakest slices are available yet.",
    )

    st.markdown("#### Unstable / Sample-Limited Slices")
    _render_table(
        _hypothesis_edge_slice_rows(unstable[:10]),
        empty_message="No unstable slice warnings are available yet.",
    )

    sample_warnings = [
        warning
        for warning in summary.get("warnings", [])
        if "sample size" in str(warning).lower() or "minimum sample" in str(warning).lower()
    ]
    _render_text_list("Sample-Size Warnings", sample_warnings)
    _render_text_list("Edge Slicing Warnings", summary.get("warnings", []))

    st.markdown("#### Slice Rows")
    _render_table(
        _hypothesis_edge_slice_rows(filtered_rows or slice_rows),
        empty_message="No edge slice rows match the selected filters.",
    )

    st.markdown("#### Edge Slicing Summary History")
    _render_table(
        _hypothesis_edge_summary_rows(getattr(data, "recent_hypothesis_edge_slice_summaries", [])),
        empty_message="No persisted edge slicing summary history is available yet.",
    )

    st.caption(
        "Candidate labels here are review-only heuristics. They do not promote paper trading, create orders, or enable execution."
    )
    st.caption(
        f"Current slice thresholds: strong>={config.strong_favorable_rate:.0%}, weak>={config.weak_favorable_rate:.0%}, "
        f"max unfavorable<={config.max_unfavorable_rate:.0%}, min samples={config.min_samples_per_slice}."
    )


def _coerce_hypothesis_edge_config(raw_config: Any) -> HypothesisEdgeSlicingConfig:
    if isinstance(raw_config, HypothesisEdgeSlicingConfig):
        return raw_config
    if isinstance(raw_config, dict):
        raw_thresholds = raw_config.get("max_avg_adverse_move_pct", {})
        thresholds = {"BTC": 1.5, "Gold": 0.8}
        if isinstance(raw_thresholds, dict):
            for asset_key, default_value in thresholds.items():
                thresholds[asset_key] = float(raw_thresholds.get(asset_key, default_value))
        return HypothesisEdgeSlicingConfig(
            enabled=bool(raw_config.get("enabled", False)),
            lookback_days=int(raw_config.get("lookback_days", 90)),
            min_samples_per_slice=int(raw_config.get("min_samples_per_slice", 10)),
            strong_favorable_rate=float(raw_config.get("strong_favorable_rate", 0.60)),
            weak_favorable_rate=float(raw_config.get("weak_favorable_rate", 0.45)),
            max_unfavorable_rate=float(raw_config.get("max_unfavorable_rate", 0.40)),
            max_avg_adverse_move_pct=thresholds,
        )
    return HypothesisEdgeSlicingConfig(
        enabled=False,
        lookback_days=90,
        min_samples_per_slice=10,
        strong_favorable_rate=0.60,
        weak_favorable_rate=0.45,
        max_unfavorable_rate=0.40,
        max_avg_adverse_move_pct={"BTC": 1.5, "Gold": 0.8},
    )


def _render_hypothesis_edge_filters(rows: list[dict[str, Any]]) -> dict[str, Any]:
    assets = sorted({str(row.get("asset")) for row in rows if row.get("asset")})
    families = sorted({str(row.get("strategy_family")) for row in rows if row.get("strategy_family")})
    regimes = sorted({str(row.get("regime")) for row in rows if row.get("regime")})
    horizons = sorted({int(row.get("horizon_hours")) for row in rows if row.get("horizon_hours") is not None})
    readiness_buckets = sorted({str(row.get("readiness_bucket")) for row in rows if row.get("readiness_bucket")})
    confidence_buckets = sorted({str(row.get("confidence_bucket")) for row in rows if row.get("confidence_bucket")})
    weekdays = sorted({str(row.get("weekday")) for row in rows if row.get("weekday")})
    stability_statuses = sorted({str(row.get("stability_status")) for row in rows if row.get("stability_status")})

    st.markdown("#### Edge Slice Filters")
    cols = st.columns(4)
    asset = cols[0].selectbox("Edge Asset", ["All", *assets], key="edge_asset")
    family = cols[1].selectbox("Edge Strategy Family", ["All", *families], key="edge_strategy_family")
    regime = cols[2].selectbox("Edge Regime", ["All", *regimes], key="edge_regime")
    horizon = cols[3].selectbox("Edge Horizon", ["All", *horizons], key="edge_horizon")

    cols_2 = st.columns(4)
    readiness_bucket = cols_2[0].selectbox(
        "Edge Readiness Bucket",
        ["All", *readiness_buckets],
        key="edge_readiness_bucket",
    )
    confidence_bucket = cols_2[1].selectbox(
        "Confidence Bucket",
        ["All", *confidence_buckets],
        key="edge_confidence_bucket",
    )
    weekday = cols_2[2].selectbox("Weekday", ["All", *weekdays], key="edge_weekday")
    stability_status = cols_2[3].selectbox(
        "Stability Status",
        ["All", *stability_statuses],
        key="edge_stability_status",
    )

    return {
        "asset": None if asset == "All" else asset,
        "strategy_family": None if family == "All" else family,
        "regime": None if regime == "All" else regime,
        "horizon_hours": None if horizon == "All" else int(horizon),
        "readiness_bucket": None if readiness_bucket == "All" else readiness_bucket,
        "confidence_bucket": None if confidence_bucket == "All" else confidence_bucket,
        "weekday": None if weekday == "All" else weekday,
        "stability_status": None if stability_status == "All" else stability_status,
    }


def _filter_hypothesis_edge_rows(
    rows: list[dict[str, Any]],
    *,
    asset: str | None = None,
    strategy_family: str | None = None,
    regime: str | None = None,
    horizon_hours: int | None = None,
    readiness_bucket: str | None = None,
    confidence_bucket: str | None = None,
    weekday: str | None = None,
    stability_status: str | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if asset and str(row.get("asset")) != asset:
            continue
        if strategy_family and str(row.get("strategy_family")) != strategy_family:
            continue
        if regime and str(row.get("regime")) != regime:
            continue
        if horizon_hours is not None and int(row.get("horizon_hours") or 0) != int(horizon_hours):
            continue
        if readiness_bucket and str(row.get("readiness_bucket")) != readiness_bucket:
            continue
        if confidence_bucket and str(row.get("confidence_bucket")) != confidence_bucket:
            continue
        if weekday and str(row.get("weekday")) != weekday:
            continue
        if stability_status and str(row.get("stability_status")) != stability_status:
            continue
        filtered.append(row)
    return filtered


def _hypothesis_edge_slice_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted_rows: list[dict[str, Any]] = []
    for row in rows:
        warnings = row.get("warnings", [])
        if isinstance(warnings, list):
            warning_text = "; ".join(str(item) for item in warnings if str(item).strip())
        else:
            warning_text = str(warnings or "")
        formatted_rows.append(
            {
                "slice_key": row.get("slice_key"),
                "asset": row.get("asset"),
                "strategy_family": row.get("strategy_family"),
                "regime": row.get("regime"),
                "horizon_hours": row.get("horizon_hours"),
                "readiness_bucket": row.get("readiness_bucket"),
                "confidence_bucket": row.get("confidence_bucket"),
                "weekday": row.get("weekday"),
                "sample_size": row.get("sample_size"),
                "favorable_count": row.get("favorable_count"),
                "unfavorable_count": row.get("unfavorable_count"),
                "neutral_count": row.get("neutral_count"),
                "favorable_rate": _format_ratio(row.get("favorable_rate")),
                "unfavorable_rate": _format_ratio(row.get("unfavorable_rate")),
                "neutral_rate": _format_ratio(row.get("neutral_rate")),
                "avg_move_pct": _format_metric(row.get("avg_move_pct")),
                "avg_max_favorable_move_pct": _format_metric(row.get("avg_max_favorable_move_pct")),
                "avg_max_adverse_move_pct": _format_metric(row.get("avg_max_adverse_move_pct")),
                "stability_status": row.get("stability_status"),
                "candidate_status": row.get("candidate_status"),
                "warnings": warning_text or None,
            }
        )
    return formatted_rows


def _hypothesis_edge_summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted_rows: list[dict[str, Any]] = []
    for row in rows:
        formatted_rows.append(
            {
                "created_at": row.get("generated_at") or row.get("created_at"),
                "lookback_days": row.get("lookback_days"),
                "total_slices": row.get("total_slices"),
                "strongest_slices": len(row.get("strongest_slices", [])) if isinstance(row.get("strongest_slices"), list) else 0,
                "weakest_slices": len(row.get("weakest_slices", [])) if isinstance(row.get("weakest_slices"), list) else 0,
                "unstable_slices": len(row.get("unstable_slices", [])) if isinstance(row.get("unstable_slices"), list) else 0,
            }
        )
    return formatted_rows


def _summary_export_row(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": summary.get("id"),
        "created_at": summary.get("created_at"),
        "lookback_days": summary.get("lookback_days"),
        "total_outcomes": summary.get("total_outcomes"),
        "evaluated_outcomes": summary.get("evaluated_outcomes"),
        "favorable_count": summary.get("favorable_count"),
        "unfavorable_count": summary.get("unfavorable_count"),
        "neutral_count": summary.get("neutral_count"),
        "insufficient_followup_count": summary.get("insufficient_followup_count"),
        "blocked_not_evaluated_count": summary.get("blocked_not_evaluated_count"),
        "favorable_rate": summary.get("favorable_rate"),
        "unfavorable_rate": summary.get("unfavorable_rate"),
        "neutral_rate": summary.get("neutral_rate"),
        "by_asset_json": summary.get("by_asset"),
        "by_strategy_family_json": summary.get("by_strategy_family"),
        "by_regime_json": summary.get("by_regime"),
        "by_horizon_json": summary.get("by_horizon"),
        "by_readiness_bucket_json": summary.get("by_readiness_bucket"),
        "by_hypothesis_status_json": summary.get("by_hypothesis_status"),
        "avg_move_pct": summary.get("avg_move_pct"),
        "avg_max_favorable_move_pct": summary.get("avg_max_favorable_move_pct"),
        "avg_max_adverse_move_pct": summary.get("avg_max_adverse_move_pct"),
        "promoted_candidates_json": summary.get("promoted_candidates"),
        "blocked_candidates_json": summary.get("blocked_candidates"),
        "candidate_progress_json": summary.get("candidate_progress"),
        "warnings_json": summary.get("warnings"),
    }


def _format_metric(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _format_ratio(value: Any) -> str:
    try:
        return f"{float(value or 0.0):.0%}"
    except (TypeError, ValueError):
        return "0%"


def _render_readiness_card(column, row: dict[str, Any] | None, min_score: int) -> None:
    if row is None:
        column.info("No readiness data available yet.")
        return
    decision_ready = bool(row.get("decision_ready"))
    column.metric(
        f"{row.get('asset')} Readiness",
        f"{row.get('readiness_score', 0)}/100",
        "READY" if decision_ready else "NO-TRADE",
    )
    column.caption(
        f"Regime: {row.get('regime')} | Completeness: {row.get('data_completeness')}% | "
        f"Minimum Score: {min_score}"
    )


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _paper_profile_options(data: DashboardData) -> list[str]:
    data = _coerce_dashboard_data(data)
    options = {
        "conservative",
        "balanced",
        "exploratory",
    }
    current_profile = str((data.paper_signal_config or {}).get("profile") or "").strip()
    if current_profile:
        options.add(current_profile)
    for row in data.paper_recent_signal_reviews:
        profile = str(row.get("active_profile") or "").strip()
        if profile:
            options.add(profile)
    return sorted(options)


def _coerce_dashboard_data(data: DashboardData | Any) -> DashboardData:
    if isinstance(data, DashboardData):
        return data

    values: dict[str, Any] = {}
    for field_name, field_def in DashboardData.__dataclass_fields__.items():
        if hasattr(data, field_name):
            values[field_name] = getattr(data, field_name)
            continue

        alias_value = _dashboard_alias_value(data, field_name)
        if alias_value is not MISSING:
            values[field_name] = alias_value
            continue

        if field_def.default_factory is not MISSING:
            values[field_name] = field_def.default_factory()
        elif field_def.default is not MISSING:
            values[field_name] = field_def.default
        else:
            values[field_name] = None

    return DashboardData(**values)


def _dashboard_alias_value(data: Any, field_name: str) -> Any:
    if field_name == "database_available" and hasattr(data, "sqlite_status"):
        return str(getattr(data, "sqlite_status")).strip().upper() == "OK"
    if field_name == "database_message" and hasattr(data, "sqlite_status"):
        return f"SQLite: {getattr(data, 'sqlite_status')}"

    for alias in _DASHBOARD_DATA_ALIASES.get(field_name, ()):
        if hasattr(data, alias):
            return getattr(data, alias)
    return MISSING


def _render_market_charts(chart_rows: list[dict[str, Any]]) -> None:
    chart_specs = [
        ("BTC Price", "BTC", "price"),
        ("Fear & Greed", "BTC", "fear_and_greed_index"),
        ("BTC Funding Rate", "BTC", "funding_rate"),
        ("BTC Open Interest", "BTC", "open_interest"),
        ("Gold US10Y", "Gold", "us10y"),
        ("Gold Real Yield", "Gold", "real_yield"),
    ]

    rendered_any = False
    for title, asset, data_type in chart_specs:
        rows = filter_rows(chart_rows, asset=asset, data_type=data_type)
        if not rows:
            continue
        rendered_any = True
        st.markdown(f"#### {title}")
        st.line_chart(rows, x="timestamp", y="value")

    if not rendered_any:
        st.info("No chartable market data matches the selected filters.")


def _render_score_charts(chart_rows: list[dict[str, Any]]) -> None:
    assets = sorted({str(row.get("asset")) for row in chart_rows if row.get("asset")})
    if not assets:
        st.info("No chartable score data matches the selected filters.")
        return

    for asset in assets:
        rows = filter_rows(chart_rows, asset=asset)
        if rows:
            st.markdown(f"#### {asset} Score")
            st.line_chart(rows, x="timestamp", y="total_score")


def _render_download_button(label: str, rows: list[dict[str, Any]], file_name: str) -> None:
    if not rows:
        st.caption(f"{label}: no rows available to export.")
        return
    st.download_button(
        label=label,
        data=rows_to_csv(rows),
        file_name=file_name,
        mime="text/csv",
    )


def _market_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "asset": row.get("asset"),
            "data_type": row.get("data_type"),
            "source": row.get("source"),
            "status": row.get("status"),
            "timestamp": row.get("timestamp"),
            "value": row.get("display_value"),
            "error_summary": row.get("error_summary"),
        }
        for row in rows
    ]


def _dict_to_rows(values: dict[str, str], key_name: str, value_name: str) -> list[dict[str, str]]:
    return [{key_name: key, value_name: value} for key, value in values.items()]


def _render_key_value_grid(values: dict[str, Any]) -> None:
    rows = [{"Field": key, "Value": value} for key, value in values.items()]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_table(rows: list[dict[str, Any]], empty_message: str) -> None:
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info(empty_message)


def _render_text_list(title: str, items: list[str]) -> None:
    st.markdown(f"**{title}**")
    if not items:
        st.write("None")
        return
    for item in items:
        st.write(f"- {item}")


if __name__ == "__main__":
    main()
