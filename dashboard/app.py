from __future__ import annotations

from dataclasses import MISSING
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

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


def _format_metric(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


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
