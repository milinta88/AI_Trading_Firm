from __future__ import annotations

import csv
import json
import sqlite3
from datetime import date, datetime
from dataclasses import asdict, dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

import yaml

from analytics.research_readiness import ResearchReadinessAnalyzer
from analytics.data_hygiene import DataHygieneAnalyzer
from analytics.report_archive import ArchiveQuery, ReportArchive
from analytics.trend_analyzer import TrendAnalyzer
from core.config import (
    DEFAULT_RESEARCH_STALE_AFTER_MINUTES,
    PAPER_SIGNAL_PROFILE_PRESETS,
    ResearchReadinessConfig,
)
from paper_trading.analytics import PaperAnalytics


def _default_data_hygiene_summary() -> dict[str, Any]:
    return {
        "total_market_snapshots": 0,
        "total_score_snapshots": 0,
        "latest_market_snapshot_timestamp": None,
        "latest_score_snapshot_timestamp": None,
        "warning_count": 0,
        "fail_count": 0,
    }


def _default_paper_analytics_summary(starting_equity: float = 10_000.0) -> dict[str, Any]:
    return {
        "starting_equity": starting_equity,
        "latest_equity": starting_equity,
        "total_pnl_abs": 0.0,
        "total_pnl_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "total_orders": 0,
        "open_positions": 0,
        "closed_positions": 0,
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "profit_factor": None,
        "average_pnl": 0.0,
        "average_r_multiple": None,
    }


def _default_paper_signal_review_summary(profile: str = "conservative") -> dict[str, Any]:
    return {
        "signals_evaluated": 0,
        "signals_accepted": 0,
        "signals_rejected": 0,
        "no_trade_count": 0,
        "accepted_by_asset": {},
        "rejected_by_reason": {},
        "rejected_by_asset": {},
        "no_trade_by_reason": {},
        "no_trade_by_asset": {},
        "accepted_by_profile": {},
        "no_trade_by_profile": {},
        "active_profile": profile,
        "source_mode": "none",
        "legacy_signal_events_ignored": 0,
        "notes": [],
    }


@dataclass(frozen=True)
class DashboardData:
    database_available: bool = False
    database_message: str = ""
    database_path: Path | None = None
    app_mode: str = "research"
    execution_enabled: bool = False
    paper_trading_enabled: bool = False
    paper_trading_starting_equity: float = 10_000.0
    research_readiness_min_score: int = 70
    latest_workflow_run: dict[str, Any] | None = None
    latest_market_snapshots: list[dict[str, Any]] = field(default_factory=list)
    recent_market_snapshots: list[dict[str, Any]] = field(default_factory=list)
    latest_score_snapshots: list[dict[str, Any]] = field(default_factory=list)
    recent_score_snapshots: list[dict[str, Any]] = field(default_factory=list)
    latest_risk_snapshot: dict[str, Any] | None = None
    latest_report_text: str | None = None
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    recent_workflow_runs: list[dict[str, Any]] = field(default_factory=list)
    system_health: dict[str, str] = field(default_factory=dict)
    trend_results: list[dict[str, Any]] = field(default_factory=list)
    multi_point_trends: list[dict[str, Any]] = field(default_factory=list)
    market_chart_rows: list[dict[str, Any]] = field(default_factory=list)
    score_chart_rows: list[dict[str, Any]] = field(default_factory=list)
    archive_latest_report: dict[str, Any] | None = None
    archive_recent_reports: list[dict[str, Any]] = field(default_factory=list)
    archive_recent_messages: list[dict[str, Any]] = field(default_factory=list)
    archive_items: list[dict[str, Any]] = field(default_factory=list)
    data_hygiene_overall_status: str = "NOT_AVAILABLE"
    data_hygiene_summary: dict[str, Any] = field(default_factory=_default_data_hygiene_summary)
    data_hygiene_status_distribution: list[dict[str, Any]] = field(default_factory=list)
    data_hygiene_checks: list[dict[str, Any]] = field(default_factory=list)
    paper_latest_equity: dict[str, Any] | None = None
    paper_open_positions: list[dict[str, Any]] = field(default_factory=list)
    paper_recent_orders: list[dict[str, Any]] = field(default_factory=list)
    paper_recent_risk_events: list[dict[str, Any]] = field(default_factory=list)
    paper_equity_curve: list[dict[str, Any]] = field(default_factory=list)
    paper_closed_positions: list[dict[str, Any]] = field(default_factory=list)
    paper_latest_run_summary: dict[str, Any] | None = None
    paper_recent_run_summaries: list[dict[str, Any]] = field(default_factory=list)
    paper_analytics_summary: dict[str, Any] = field(default_factory=_default_paper_analytics_summary)
    paper_signal_review_summary: dict[str, Any] = field(
        default_factory=_default_paper_signal_review_summary
    )
    paper_pnl_by_asset: list[dict[str, Any]] = field(default_factory=list)
    paper_rejection_reasons: list[dict[str, Any]] = field(default_factory=list)
    paper_no_trade_reasons: list[dict[str, Any]] = field(default_factory=list)
    paper_recent_signal_reviews: list[dict[str, Any]] = field(default_factory=list)
    paper_journal_notes: list[dict[str, Any]] = field(default_factory=list)
    latest_research_readiness: list[dict[str, Any]] = field(default_factory=list)
    recent_research_readiness: list[dict[str, Any]] = field(default_factory=list)
    paper_signal_config: dict[str, Any] | None = field(
        default_factory=lambda: _default_paper_signal_config("conservative")
    )
    research_readiness_enabled: bool = False


def load_dashboard_data(project_root: Path, limit: int = 25) -> DashboardData:
    (
        app_mode,
        execution_enabled,
        paper_trading_enabled,
        paper_trading_starting_equity,
        paper_signal_config,
        research_readiness_config,
        database_path,
    ) = load_dashboard_config(project_root)

    if not database_path.exists():
        return _empty_dashboard_data(
            app_mode=app_mode,
            execution_enabled=execution_enabled,
            paper_trading_enabled=paper_trading_enabled,
            paper_trading_starting_equity=paper_trading_starting_equity,
            research_readiness_enabled=research_readiness_config.enabled,
            research_readiness_min_score=research_readiness_config.min_readiness_score_for_decision,
            paper_signal_config=paper_signal_config,
            message=f"Database not found at {database_path}. Run python main.py --dry-run first.",
        )

    try:
        with _connect_read_only(database_path) as connection:
            latest_market_snapshots = _fetch_latest_market_snapshots(connection)
            recent_market_snapshots = _fetch_recent_market_snapshots(connection, limit)
            latest_score_snapshots = _fetch_latest_score_snapshots(connection)
            recent_score_snapshots = _fetch_recent_score_snapshots(connection, limit)
            archive_result = _load_report_archive(database_path, limit)
            hygiene_report = _load_data_hygiene(database_path)
            paper_report = _load_paper_analytics(database_path, paper_trading_starting_equity, limit)
            readiness_report = _load_research_readiness(
                database_path=database_path,
                config=research_readiness_config,
                connection=connection,
                limit=limit,
            )
            return DashboardData(
                database_available=True,
                database_message=f"Connected read-only to {database_path}.",
                database_path=database_path,
                app_mode=app_mode,
                execution_enabled=execution_enabled,
                paper_trading_enabled=paper_trading_enabled,
                paper_trading_starting_equity=paper_trading_starting_equity,
                research_readiness_enabled=research_readiness_config.enabled,
                research_readiness_min_score=research_readiness_config.min_readiness_score_for_decision,
                paper_signal_config=paper_signal_config,
                latest_workflow_run=_fetch_latest_workflow_run(connection),
                latest_market_snapshots=latest_market_snapshots,
                recent_market_snapshots=recent_market_snapshots,
                latest_score_snapshots=latest_score_snapshots,
                recent_score_snapshots=recent_score_snapshots,
                latest_risk_snapshot=_fetch_latest_risk_snapshot(connection),
                latest_report_text=_fetch_latest_report_text(connection),
                recent_messages=_fetch_recent_messages(connection, limit),
                recent_workflow_runs=_fetch_recent_workflow_runs(connection, limit),
                system_health=_derive_system_health(connection),
                trend_results=_load_trend_results(database_path),
                multi_point_trends=_load_multi_point_trends(database_path),
                market_chart_rows=build_market_chart_rows(recent_market_snapshots),
                score_chart_rows=build_score_chart_rows(recent_score_snapshots),
                archive_latest_report=archive_result["latest_report"],
                archive_recent_reports=archive_result["recent_reports"],
                archive_recent_messages=archive_result["recent_messages"],
                archive_items=archive_result["items"],
                data_hygiene_overall_status=hygiene_report["overall_status"],
                data_hygiene_summary=hygiene_report["summary"],
                data_hygiene_status_distribution=hygiene_report["status_distribution"],
                data_hygiene_checks=hygiene_report["checks"],
                paper_latest_equity=_fetch_latest_paper_equity(connection),
                paper_open_positions=_fetch_open_paper_positions(connection),
                paper_recent_orders=_fetch_recent_paper_orders(connection, limit),
                paper_recent_risk_events=_fetch_recent_paper_risk_events(connection, limit),
                paper_equity_curve=_fetch_paper_equity_curve(connection, limit),
                paper_closed_positions=_fetch_recent_closed_paper_positions(connection, limit),
                paper_latest_run_summary=_fetch_latest_paper_run_summary(connection),
                paper_recent_run_summaries=_fetch_recent_paper_run_summaries(connection, limit),
                paper_analytics_summary=paper_report["performance"],
                paper_signal_review_summary=paper_report["signal_review"],
                paper_pnl_by_asset=paper_report["pnl_by_asset"],
                paper_rejection_reasons=paper_report["rejection_reasons"],
                paper_no_trade_reasons=paper_report["no_trade_reasons"],
                paper_recent_signal_reviews=paper_report["recent_signal_reviews"],
                paper_journal_notes=_fetch_recent_paper_journal_notes(connection, limit),
                latest_research_readiness=readiness_report["latest"],
                recent_research_readiness=readiness_report["recent"],
            )
    except sqlite3.Error as exc:
        return _empty_dashboard_data(
            app_mode=app_mode,
            execution_enabled=execution_enabled,
            paper_trading_enabled=paper_trading_enabled,
            paper_trading_starting_equity=paper_trading_starting_equity,
            research_readiness_enabled=research_readiness_config.enabled,
            research_readiness_min_score=research_readiness_config.min_readiness_score_for_decision,
            paper_signal_config=paper_signal_config,
            message=f"Unable to read dashboard database: {exc}",
        )


def load_dashboard_config(
    project_root: Path,
) -> tuple[str, bool, bool, float, dict[str, Any], ResearchReadinessConfig, Path]:
    config_path = project_root / "config.yaml"
    if not config_path.exists():
        return (
            "research",
            False,
            False,
            10_000.0,
            _default_paper_signal_config(),
            _default_research_readiness_config(),
            project_root / "data" / "database.db",
        )

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            raw_config = yaml.safe_load(handle) or {}
    except Exception:
        return (
            "research",
            False,
            False,
            10_000.0,
            _default_paper_signal_config(),
            _default_research_readiness_config(),
            project_root / "data" / "database.db",
        )

    app_section = raw_config.get("app", {})
    risk_section = raw_config.get("risk", {})
    paper_trading_section = raw_config.get("paper_trading", {})
    paper_signal_section = raw_config.get("paper_signal", {})
    research_readiness_section = raw_config.get("research_readiness", {})
    database_section = raw_config.get("database", {})
    database_path = Path(str(database_section.get("path", "data/database.db")))
    if not database_path.is_absolute():
        database_path = project_root / database_path

    try:
        return (
            str(app_section.get("mode", "research")).strip().lower() or "research",
            _as_bool(risk_section.get("execution_enabled", False)),
            _as_bool(paper_trading_section.get("enabled", False)),
            float(paper_trading_section.get("starting_equity", 10_000)),
            _load_paper_signal_config(paper_signal_section),
            _load_research_readiness_config(research_readiness_section),
            database_path,
        )
    except Exception:
        return (
            "research",
            False,
            False,
            10_000.0,
            _default_paper_signal_config(),
            _default_research_readiness_config(),
            database_path,
        )


def parse_json_value(raw_value: str | None, fallback: Any = None) -> Any:
    if raw_value in {None, ""}:
        return fallback
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return fallback


def format_snapshot_value(row: dict[str, Any]) -> str:
    value = parse_json_value(row.get("value_json"), fallback=None)
    if not isinstance(value, dict):
        return "N/A"

    if "price" in value:
        return f"{float(value['price']):,.2f} USDT"
    if "value" in value and "classification" in value:
        return f"{value['value']} ({value['classification']})"
    if "funding_rate" in value:
        return f"{float(value['funding_rate']) * 100:.4f}%"
    if "open_interest" in value:
        return f"{float(value['open_interest']):,.3f}"
    if "latest_value" in value:
        observation_date = value.get("observation_date", "unknown date")
        return f"{value['latest_value']} ({observation_date})"

    return json.dumps(value, sort_keys=True)


def parse_score_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(row)
    parsed["components"] = parse_json_value(row.get("components_json"), fallback=[])
    parsed["reasons"] = parse_json_value(row.get("reasons_json"), fallback=[])
    parsed["warnings"] = parse_json_value(row.get("warnings_json"), fallback=[])
    return parsed


def build_market_chart_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chart_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "OK":
            continue
        numeric_value = _numeric_market_value(row)
        if numeric_value is None:
            continue
        chart_rows.append(
            {
                "timestamp": row.get("timestamp"),
                "asset": row.get("asset"),
                "data_type": row.get("data_type"),
                "source": row.get("source"),
                "status": row.get("status"),
                "value": numeric_value,
            }
        )
    return sorted(chart_rows, key=lambda item: str(item.get("timestamp") or ""))


def build_score_chart_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chart_rows: list[dict[str, Any]] = []
    for row in rows:
        try:
            score = float(row["total_score"])
        except (KeyError, TypeError, ValueError):
            continue
        chart_rows.append(
            {
                "timestamp": row.get("timestamp"),
                "asset": row.get("asset"),
                "total_score": score,
                "bias": row.get("bias"),
                "confidence": row.get("confidence"),
                "data_completeness": row.get("data_completeness"),
            }
        )
    return sorted(chart_rows, key=lambda item: str(item.get("timestamp") or ""))


def filter_rows(
    rows: list[dict[str, Any]],
    start_date: date | None = None,
    end_date: date | None = None,
    asset: str | None = None,
    data_type: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    normalized_asset = _normalize_filter_value(asset)
    normalized_data_type = _normalize_filter_value(data_type)
    filtered_rows: list[dict[str, Any]] = []

    for row in rows:
        if normalized_asset and str(row.get("asset")) != normalized_asset:
            continue
        if normalized_data_type and str(row.get("data_type")) != normalized_data_type:
            continue

        row_date = _row_date(row)
        if start_date and row_date and row_date < start_date:
            continue
        if end_date and row_date and row_date > end_date:
            continue
        if (start_date or end_date) and row_date is None:
            continue

        filtered_rows.append(row)
        if limit is not None and len(filtered_rows) >= limit:
            break

    return filtered_rows


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""

    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_cell(row.get(key)) for key in fieldnames})
    return output.getvalue()


def _empty_dashboard_data(
    app_mode: str,
    execution_enabled: bool,
    paper_trading_enabled: bool,
    paper_trading_starting_equity: float,
    research_readiness_enabled: bool,
    research_readiness_min_score: int,
    paper_signal_config: dict[str, Any],
    message: str,
) -> DashboardData:
    paper_signal_config = paper_signal_config or _default_paper_signal_config()
    return DashboardData(
        database_available=False,
        database_message=message,
        database_path=None,
        app_mode=app_mode,
        execution_enabled=execution_enabled,
        paper_trading_enabled=paper_trading_enabled,
        paper_trading_starting_equity=paper_trading_starting_equity,
        research_readiness_enabled=research_readiness_enabled,
        research_readiness_min_score=research_readiness_min_score,
        paper_signal_config=paper_signal_config,
        paper_analytics_summary=_default_paper_analytics_summary(paper_trading_starting_equity),
        paper_signal_review_summary=_default_paper_signal_review_summary(
            str(paper_signal_config.get("profile") or "conservative")
        ),
    )


def _load_trend_results(database_path: Path) -> list[dict[str, Any]]:
    trends = TrendAnalyzer(database_path).analyze_all()
    return [
        {"key": key, **asdict(result)}
        for key, result in trends.items()
    ]


def _load_multi_point_trends(database_path: Path) -> list[dict[str, Any]]:
    trends = TrendAnalyzer(database_path).analyze_all_multipoint()
    return [
        {"key": key, **asdict(result)}
        for key, result in trends.items()
    ]


def _load_report_archive(database_path: Path, limit: int) -> dict[str, Any]:
    archive = ReportArchive(database_path).load(ArchiveQuery(limit=limit))
    return {
        "latest_report": asdict(archive.latest_report) if archive.latest_report else None,
        "recent_reports": [asdict(item) for item in archive.recent_reports],
        "recent_messages": [asdict(item) for item in archive.recent_messages],
        "items": [asdict(item) for item in archive.items],
    }


def _load_data_hygiene(database_path: Path) -> dict[str, Any]:
    report = DataHygieneAnalyzer(database_path).analyze()
    return {
        "overall_status": report.overall_status,
        "summary": report.summary,
        "status_distribution": report.status_distribution,
        "checks": [asdict(check) for check in report.checks],
    }


def _load_paper_analytics(database_path: Path, starting_equity: float, limit: int) -> dict[str, Any]:
    report = PaperAnalytics(database_path=database_path, starting_equity=starting_equity).build_report(limit=limit)
    return {
        "performance": asdict(report.performance),
        "signal_review": asdict(report.signal_review),
        "pnl_by_asset": report.pnl_by_asset,
        "rejection_reasons": report.rejection_reasons,
        "no_trade_reasons": report.no_trade_reasons,
        "recent_signal_reviews": report.recent_signal_reviews,
    }


def _load_research_readiness(
    database_path: Path,
    config: ResearchReadinessConfig,
    connection: sqlite3.Connection,
    limit: int,
) -> dict[str, Any]:
    recent_rows = _fetch_recent_research_readiness(connection, limit)
    latest_rows = _fetch_latest_research_readiness(connection)
    if not latest_rows:
        latest_rows = _build_dynamic_research_readiness_rows(database_path, config)
    return {
        "latest": latest_rows,
        "recent": recent_rows,
    }


def _load_paper_signal_config(raw_config: object) -> dict[str, Any]:
    section = raw_config if isinstance(raw_config, dict) else {}
    profile = str(section.get("profile", "conservative")).strip().lower() or "conservative"
    defaults = _default_paper_signal_config(profile)
    merged = {**defaults, **section}
    merged["profile"] = profile
    merged["allow_neutral_bias"] = _as_bool(merged.get("allow_neutral_bias", False))
    merged["exploratory_mode"] = _as_bool(merged.get("exploratory_mode", False))
    return merged


def _load_research_readiness_config(raw_config: object) -> ResearchReadinessConfig:
    section = raw_config if isinstance(raw_config, dict) else {}
    raw_stale_after = section.get("stale_after_minutes", {})
    stale_after_minutes = dict(DEFAULT_RESEARCH_STALE_AFTER_MINUTES)
    if isinstance(raw_stale_after, dict):
        for key, default_value in DEFAULT_RESEARCH_STALE_AFTER_MINUTES.items():
            stale_after_minutes[key] = int(raw_stale_after.get(key, default_value))

    return ResearchReadinessConfig(
        enabled=_as_bool(section.get("enabled", False)),
        min_snapshots_for_regime=int(section.get("min_snapshots_for_regime", 10)),
        stale_after_minutes=stale_after_minutes,
        min_readiness_score_for_decision=int(section.get("min_readiness_score_for_decision", 70)),
    )


def _default_paper_signal_config(profile: str = "conservative") -> dict[str, Any]:
    preset = PAPER_SIGNAL_PROFILE_PRESETS.get(profile, PAPER_SIGNAL_PROFILE_PRESETS["conservative"])
    return {
        "profile": profile,
        "btc_long_score_threshold": int(preset["btc_long_score_threshold"]),
        "btc_short_score_threshold": int(preset["btc_short_score_threshold"]),
        "gold_long_score_threshold": int(preset["gold_long_score_threshold"]),
        "gold_short_score_threshold": int(preset["gold_short_score_threshold"]),
        "min_confidence": str(preset["min_confidence"]),
        "min_btc_data_completeness": int(preset["min_btc_data_completeness"]),
        "min_gold_data_completeness": int(preset["min_gold_data_completeness"]),
        "allow_neutral_bias": bool(preset["allow_neutral_bias"]),
        "exploratory_mode": bool(preset["exploratory_mode"]),
    }


def _default_research_readiness_config() -> ResearchReadinessConfig:
    return ResearchReadinessConfig(
        enabled=False,
        min_snapshots_for_regime=10,
        stale_after_minutes=dict(DEFAULT_RESEARCH_STALE_AFTER_MINUTES),
        min_readiness_score_for_decision=70,
    )


def _numeric_market_value(row: dict[str, Any]) -> float | None:
    value = parse_json_value(row.get("value_json"), fallback=None)
    if not isinstance(value, dict):
        return None

    for key in ("price", "value", "funding_rate", "open_interest", "latest_value"):
        if key not in value:
            continue
        try:
            return float(value[key])
        except (TypeError, ValueError):
            return None
    return None


def _normalize_filter_value(value: str | None) -> str | None:
    if value in {None, "", "All"}:
        return None
    return str(value)


def _row_date(row: dict[str, Any]) -> date | None:
    raw_value = row.get("timestamp") or row.get("created_at") or row.get("completed_at")
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


def _csv_cell(value: Any) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, (str, int, float)):
        return value
    return str(value)


def _connect_read_only(database_path: Path) -> sqlite3.Connection:
    uri = f"{database_path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _fetch_all(connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, params).fetchall()]


def _fetch_one(connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = connection.execute(query, params).fetchone()
    return dict(row) if row else None


def _fetch_latest_workflow_run(connection: sqlite3.Connection) -> dict[str, Any] | None:
    if not _table_exists(connection, "workflow_runs"):
        return None
    return _fetch_one(connection, "SELECT * FROM workflow_runs ORDER BY id DESC LIMIT 1")


def _fetch_recent_workflow_runs(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "workflow_runs"):
        return []
    return _fetch_all(connection, "SELECT * FROM workflow_runs ORDER BY id DESC LIMIT ?", (limit,))


def _fetch_latest_market_snapshots(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(connection, "market_snapshots"):
        return []

    rows = _fetch_all(connection, "SELECT * FROM market_snapshots ORDER BY id DESC")
    latest_by_source: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["asset"]), str(row["data_type"]))
        if key not in latest_by_source:
            row["display_value"] = format_snapshot_value(row)
            latest_by_source[key] = row

    return list(latest_by_source.values())


def _fetch_recent_market_snapshots(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "market_snapshots"):
        return []
    rows = _fetch_all(connection, "SELECT * FROM market_snapshots ORDER BY id DESC LIMIT ?", (limit,))
    for row in rows:
        row["display_value"] = format_snapshot_value(row)
    return rows


def _fetch_latest_score_snapshots(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(connection, "score_snapshots"):
        return []

    rows = _fetch_all(connection, "SELECT * FROM score_snapshots ORDER BY id DESC")
    latest_by_asset: dict[str, dict[str, Any]] = {}
    for row in rows:
        asset = str(row["asset"])
        if asset not in latest_by_asset:
            latest_by_asset[asset] = parse_score_snapshot(row)

    return list(latest_by_asset.values())


def _fetch_recent_score_snapshots(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "score_snapshots"):
        return []
    rows = _fetch_all(connection, "SELECT * FROM score_snapshots ORDER BY id DESC LIMIT ?", (limit,))
    return [parse_score_snapshot(row) for row in rows]


def _fetch_latest_risk_snapshot(connection: sqlite3.Connection) -> dict[str, Any] | None:
    if not _table_exists(connection, "risk_snapshots"):
        return None
    row = _fetch_one(connection, "SELECT * FROM risk_snapshots ORDER BY id DESC LIMIT 1")
    if row:
        row["notes"] = parse_json_value(row.get("notes_json"), fallback=[])
    return row


def _fetch_latest_report_text(connection: sqlite3.Connection) -> str | None:
    if not _table_exists(connection, "workflow_runs"):
        return None
    row = _fetch_one(
        connection,
        """
        SELECT report_text
        FROM workflow_runs
        WHERE report_text IS NOT NULL AND report_text != ''
        ORDER BY id DESC
        LIMIT 1
        """,
    )
    return str(row["report_text"]) if row and row.get("report_text") else None


def _fetch_recent_messages(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "outbound_messages"):
        return []
    return _fetch_all(connection, "SELECT * FROM outbound_messages ORDER BY id DESC LIMIT ?", (limit,))


def _fetch_latest_paper_equity(connection: sqlite3.Connection) -> dict[str, Any] | None:
    if not _table_exists(connection, "paper_equity_curve"):
        return None
    return _fetch_one(connection, "SELECT * FROM paper_equity_curve ORDER BY id DESC LIMIT 1")


def _fetch_open_paper_positions(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(connection, "paper_positions"):
        return []
    rows = _fetch_all(
        connection,
        "SELECT * FROM paper_positions WHERE status = 'OPEN' ORDER BY id DESC",
    )
    for row in rows:
        row["reasons"] = parse_json_value(row.get("reason_json"), fallback=[])
    return rows


def _fetch_recent_closed_paper_positions(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "paper_positions"):
        return []
    rows = _fetch_all(
        connection,
        "SELECT * FROM paper_positions WHERE status != 'OPEN' ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    for row in rows:
        row["reasons"] = parse_json_value(row.get("reason_json"), fallback=[])
    return rows


def _fetch_recent_paper_orders(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "paper_orders"):
        return []
    rows = _fetch_all(connection, "SELECT * FROM paper_orders ORDER BY id DESC LIMIT ?", (limit,))
    for row in rows:
        row["reasons"] = parse_json_value(row.get("reason_json"), fallback=[])
        row["warnings"] = parse_json_value(row.get("warnings_json"), fallback=[])
    return rows


def _fetch_recent_paper_risk_events(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "paper_risk_events"):
        return []
    rows = _fetch_all(connection, "SELECT * FROM paper_risk_events ORDER BY id DESC LIMIT ?", (limit,))
    for row in rows:
        row["details"] = parse_json_value(row.get("details_json"), fallback={})
    return rows


def _fetch_paper_equity_curve(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "paper_equity_curve"):
        return []
    rows = _fetch_all(connection, "SELECT * FROM paper_equity_curve ORDER BY id DESC LIMIT ?", (limit,))
    return list(reversed(rows))


def _fetch_latest_paper_run_summary(connection: sqlite3.Connection) -> dict[str, Any] | None:
    if not _table_exists(connection, "paper_run_summaries"):
        return None
    row = _fetch_one(connection, "SELECT * FROM paper_run_summaries ORDER BY id DESC LIMIT 1")
    if row:
        row["notes"] = parse_json_value(row.get("notes_json"), fallback=[])
    return row


def _fetch_recent_paper_run_summaries(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "paper_run_summaries"):
        return []
    rows = _fetch_all(connection, "SELECT * FROM paper_run_summaries ORDER BY id DESC LIMIT ?", (limit,))
    for row in rows:
        row["notes"] = parse_json_value(row.get("notes_json"), fallback=[])
    return rows


def _fetch_recent_paper_journal_notes(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "paper_journal_notes"):
        return []
    return _fetch_all(
        connection,
        """
        SELECT * FROM paper_journal_notes
        WHERE is_deleted = 0
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )


def _fetch_latest_research_readiness(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(connection, "research_readiness_snapshots"):
        return []

    rows = _fetch_all(connection, "SELECT * FROM research_readiness_snapshots ORDER BY id DESC")
    latest_by_asset: dict[str, dict[str, Any]] = {}
    for row in rows:
        asset = str(row.get("asset") or "UNKNOWN")
        if asset not in latest_by_asset:
            latest_by_asset[asset] = _parse_research_readiness_snapshot(row)
    return list(latest_by_asset.values())


def _fetch_recent_research_readiness(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "research_readiness_snapshots"):
        return []
    rows = _fetch_all(
        connection,
        "SELECT * FROM research_readiness_snapshots ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [_parse_research_readiness_snapshot(row) for row in rows]


def _parse_research_readiness_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(row)
    parsed["decision_ready"] = bool(parsed.get("decision_ready"))
    parsed["stale_sources"] = parse_json_value(row.get("stale_sources_json"), fallback=[])
    parsed["missing_sources"] = parse_json_value(row.get("missing_sources_json"), fallback=[])
    parsed["warnings"] = parse_json_value(row.get("warnings_json"), fallback=[])
    parsed["no_trade_reasons"] = parse_json_value(row.get("no_trade_reasons_json"), fallback=[])
    return parsed


def _build_dynamic_research_readiness_rows(
    database_path: Path,
    config: ResearchReadinessConfig,
) -> list[dict[str, Any]]:
    results = ResearchReadinessAnalyzer(database_path=database_path, config=config).analyze_all()
    rows: list[dict[str, Any]] = []
    for asset in ("BTC", "Gold"):
        result = results.get(asset)
        if result is None:
            continue
        rows.append(
            {
                "id": None,
                "workflow_run_id": None,
                "asset": result.asset,
                "readiness_score": result.readiness_score,
                "regime": result.regime,
                "data_completeness": result.data_completeness,
                "decision_ready": result.decision_ready,
                "stale_sources": result.stale_sources,
                "missing_sources": result.missing_sources,
                "warnings": result.warnings,
                "no_trade_reasons": result.no_trade_reasons,
                "created_at": None,
            }
        )
    return rows


def _derive_system_health(connection: sqlite3.Connection) -> dict[str, str]:
    latest_market = _fetch_latest_market_snapshots(connection)
    market_status = {
        f"{row['asset']} {row['data_type']}": row["status"]
        for row in latest_market
    }
    return {
        "SQLite": "OK",
        "BTC public data": str(market_status.get("BTC price", "NOT_AVAILABLE")),
        "Fear & Greed": str(market_status.get("BTC fear_and_greed_index", "NOT_AVAILABLE")),
        "BTC derivatives data": _aggregate_status(
            [
                str(market_status.get("BTC funding_rate", "NOT_AVAILABLE")),
                str(market_status.get("BTC open_interest", "NOT_AVAILABLE")),
            ]
        ),
        "FRED": _aggregate_status(
            [
                str(market_status.get("Gold us10y", "NOT_CONFIGURED")),
                str(market_status.get("Gold real_yield", "NOT_CONFIGURED")),
                str(market_status.get("Gold fed_funds", "NOT_CONFIGURED")),
                str(market_status.get("Gold cpi", "NOT_CONFIGURED")),
            ]
        ),
        "Gold macro data": _aggregate_status(
            [
                str(market_status.get("Gold us10y", "NOT_CONFIGURED")),
                str(market_status.get("Gold real_yield", "NOT_CONFIGURED")),
                str(market_status.get("Gold fed_funds", "NOT_CONFIGURED")),
                str(market_status.get("Gold cpi", "NOT_CONFIGURED")),
                str(market_status.get("Gold dxy", "NOT_CONFIGURED")),
                str(market_status.get("Gold spot_price", "NOT_CONFIGURED")),
            ]
        ),
        "MT5": "NOT_CONFIGURED",
        "Exchange private API": "NOT_CONFIGURED",
    }


def _aggregate_status(statuses: list[str]) -> str:
    if all(status == "OK" for status in statuses):
        return "OK"
    if all(status == "NOT_CONFIGURED" for status in statuses):
        return "NOT_CONFIGURED"
    if any(status in {"FAIL", "NOT_AVAILABLE", "STALE"} for status in statuses):
        return "WARNING"
    if any(status == "NOT_CONFIGURED" for status in statuses):
        return "WARNING"
    return "UNKNOWN"


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
