from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import dashboard.app as dashboard_app
from dashboard.data_loader import DashboardData, load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loader_handles_missing_research_readiness_table(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("DROP TABLE research_readiness_snapshots")

    data = load_dashboard_data(tmp_path)

    assert data.database_available is True
    assert data.research_readiness_enabled is True
    assert {row["asset"] for row in data.latest_research_readiness} == {"BTC", "Gold"}
    assert data.recent_research_readiness == []


def test_dashboard_loader_reads_persisted_research_readiness_history(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-06-01', 'research', 'COMPLETED')
            """
        )
        connection.execute(
            """
            INSERT INTO research_readiness_snapshots (
                workflow_run_id, asset, readiness_score, regime, data_completeness, decision_ready,
                stale_sources_json, missing_sources_json, warnings_json, no_trade_reasons_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "BTC",
                82,
                "TREND_UP",
                100,
                1,
                json.dumps([]),
                json.dumps([]),
                json.dumps(["Read-only regime classification from persisted snapshots."]),
                json.dumps([]),
                datetime(2026, 6, 1, 1, 0, tzinfo=UTC).isoformat(),
            ),
        )

    data = load_dashboard_data(tmp_path)

    assert data.latest_research_readiness[0]["asset"] == "BTC"
    assert data.latest_research_readiness[0]["decision_ready"] is True
    assert data.recent_research_readiness[0]["regime"] == "TREND_UP"


def test_dashboard_data_has_safe_research_readiness_enabled_default() -> None:
    assert DashboardData.__dataclass_fields__["research_readiness_enabled"].default is False


def test_dashboard_loader_defaults_readiness_disabled_when_config_is_missing(tmp_path: Path) -> None:
    data = load_dashboard_data(tmp_path)

    assert data.database_available is False
    assert data.research_readiness_enabled is False
    assert data.paper_signal_config is not None


def test_dashboard_render_functions_handle_empty_dashboard_data(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(dashboard_app, "st", fake_st)

    data = DashboardData()
    filters = {
        "asset": None,
        "data_type": None,
        "start_date": None,
        "end_date": None,
        "limit": 25,
    }

    dashboard_app._render_status_header(data)
    dashboard_app._render_overview(data)
    dashboard_app._render_market_snapshots(data, filters)
    dashboard_app._render_trend_context(data, filters)
    dashboard_app._render_research_readiness(data)
    dashboard_app._render_score_snapshots(data, filters)
    dashboard_app._render_daily_brief(data)
    dashboard_app._render_report_archive(data)
    dashboard_app._render_data_hygiene(data)
    dashboard_app._render_paper_trading(data)
    dashboard_app._render_safety_view(data)

    assert "Research readiness is disabled in config." in fake_st.infos
    assert "SIMULATED ONLY - NO REAL TRADING - WATCH ONLY" in fake_st.errors
    assert "EXECUTION DISABLED" in fake_st.errors


def test_research_readiness_renderer_handles_missing_enabled_field(
    monkeypatch,
) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(dashboard_app, "st", fake_st)

    legacy_data = SimpleNamespace(
        latest_research_readiness=[],
        recent_research_readiness=[],
        research_readiness_min_score=70,
    )

    dashboard_app._render_research_readiness(legacy_data)

    assert "Research readiness is disabled in config." in fake_st.infos


def test_paper_trading_renderer_does_not_depend_on_research_readiness_fields(
    monkeypatch,
) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(dashboard_app, "st", fake_st)

    paper_data = SimpleNamespace(
        database_path=None,
        paper_trading_enabled=False,
        paper_trading_starting_equity=10_000.0,
        paper_signal_config={},
        paper_analytics_summary={
            "starting_equity": 10_000.0,
            "latest_equity": 10_000.0,
            "total_pnl_abs": 0.0,
            "total_pnl_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "open_positions": 0,
            "closed_positions": 0,
            "win_rate": 0.0,
            "profit_factor": None,
            "average_pnl": 0.0,
            "average_r_multiple": None,
        },
        paper_signal_review_summary={
            "signals_evaluated": 0,
            "signals_accepted": 0,
            "signals_rejected": 0,
            "no_trade_count": 0,
            "source_mode": "none",
            "legacy_signal_events_ignored": 0,
            "notes": [],
        },
        paper_latest_equity=None,
        paper_latest_run_summary=None,
        paper_equity_curve=[],
        paper_pnl_by_asset=[],
        paper_rejection_reasons=[],
        paper_no_trade_reasons=[],
        paper_recent_signal_reviews=[],
        paper_open_positions=[],
        paper_closed_positions=[],
        paper_recent_orders=[],
        paper_recent_risk_events=[],
        paper_recent_run_summaries=[],
        paper_journal_notes=[],
    )

    dashboard_app._render_paper_trading(paper_data)

    assert "SIMULATED ONLY - NO REAL TRADING - WATCH ONLY" in fake_st.errors


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "\n".join(
            [
                "app:",
                "  name: AI Trading Firm",
                "  mode: research",
                "database:",
                "  path: data/database.db",
                "risk:",
                "  execution_enabled: false",
                "research_readiness:",
                "  enabled: true",
                "  min_snapshots_for_regime: 10",
                "  stale_after_minutes:",
                "    btc_price: 60",
                "    btc_derivatives: 240",
                "    fear_and_greed: 1440",
                "    gold_macro: 4320",
                "  min_readiness_score_for_decision: 70",
            ]
        ),
        encoding="utf-8",
    )


class _FakeColumn:
    def __init__(self, streamlit: "_FakeStreamlit") -> None:
        self._streamlit = streamlit

    def metric(self, *args, **kwargs) -> None:
        self._streamlit.metric(*args, **kwargs)

    def caption(self, value) -> None:
        self._streamlit.caption(value)

    def info(self, value) -> None:
        self._streamlit.info(value)

    def selectbox(self, label, options, key=None):
        return self._streamlit.selectbox(label, options, key=key)

    def download_button(self, *args, **kwargs) -> None:
        self._streamlit.download_button(*args, **kwargs)

    def text_input(self, *args, **kwargs):
        return self._streamlit.text_input(*args, **kwargs)


class _FakeStreamlit:
    def __init__(self) -> None:
        self.infos: list[str] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.successes: list[str] = []

    def subheader(self, *_args, **_kwargs) -> None:
        return None

    def caption(self, *_args, **_kwargs) -> None:
        return None

    def markdown(self, *_args, **_kwargs) -> None:
        return None

    def info(self, value, *_args, **_kwargs) -> None:
        self.infos.append(str(value))

    def error(self, value, *_args, **_kwargs) -> None:
        self.errors.append(str(value))

    def warning(self, value, *_args, **_kwargs) -> None:
        self.warnings.append(str(value))

    def success(self, value, *_args, **_kwargs) -> None:
        self.successes.append(str(value))

    def write(self, *_args, **_kwargs) -> None:
        return None

    def dataframe(self, *_args, **_kwargs) -> None:
        return None

    def line_chart(self, *_args, **_kwargs) -> None:
        return None

    def bar_chart(self, *_args, **_kwargs) -> None:
        return None

    def download_button(self, *_args, **_kwargs) -> None:
        return None

    def selectbox(self, _label, options, key=None):
        del key
        return options[0] if options else None

    def text_input(self, *_args, **_kwargs):
        return ""

    def text_area(self, *_args, **_kwargs):
        return ""

    def date_input(self, *_args, **_kwargs):
        return ()

    def columns(self, count: int):
        return [_FakeColumn(self) for _ in range(count)]

    def metric(self, *_args, **_kwargs) -> None:
        return None

    def rerun(self) -> None:
        return None
