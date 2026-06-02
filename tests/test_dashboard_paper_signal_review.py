from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import dashboard.app as dashboard_app
from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loader_exposes_balanced_signal_config_and_normalized_reviews(tmp_path: Path) -> None:
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
        connection.executemany(
            """
            INSERT INTO paper_signal_reviews (
                workflow_run_id, asset, signal_action, review_status, bias, total_score,
                confidence, data_completeness, active_profile, signal_source, reasons_json, warnings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "BTC", "LONG", "ACCEPTED", "Bullish", 72, "Medium", 90, "balanced", "paper_signal_balanced", json.dumps([{"code": "SIGNAL_ACCEPTED", "message": "ok"}]), json.dumps(["paper only"])),
                (1, "Gold", "NO_TRADE", "NO_TRADE", "Neutral", 52, "Low", 55, "balanced", "paper_signal_balanced", json.dumps([{"code": "CONFIDENCE_TOO_LOW", "message": "low confidence"}]), "[]"),
            ],
        )

    data = load_dashboard_data(tmp_path)

    assert data.paper_signal_config["profile"] == "balanced"
    assert data.paper_signal_config["btc_long_score_threshold"] == 67
    assert data.paper_signal_config["gold_short_score_threshold"] == 38
    assert data.paper_signal_review_summary["source_mode"] == "normalized"
    assert data.paper_signal_review_summary["signals_evaluated"] == 2
    assert data.paper_signal_review_summary["signals_accepted"] == 1
    assert data.paper_signal_review_summary["no_trade_count"] == 1
    assert data.paper_no_trade_reasons == [{"reason": "CONFIDENCE_TOO_LOW", "no_trade_count": 1}]
    assert data.paper_recent_signal_reviews[0]["active_profile"] == "balanced"
    assert data.paper_recent_signal_reviews[0]["reasons"][0]["code"] in {"SIGNAL_ACCEPTED", "CONFIDENCE_TOO_LOW"}
    assert {row["review_status"] for row in data.paper_recent_signal_reviews} == {"ACCEPTED", "NO_TRADE"}


def test_dashboard_loader_returns_safe_paper_signal_defaults_when_disabled(tmp_path: Path) -> None:
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
                "paper_trading:",
                "  enabled: false",
                "  starting_equity: 10000",
            ]
        ),
        encoding="utf-8",
    )

    data = load_dashboard_data(tmp_path)

    assert data.paper_trading_enabled is False
    assert data.paper_signal_config is not None
    assert data.paper_signal_config["profile"] == "conservative"
    assert data.paper_signal_config["btc_long_score_threshold"] == 70
    assert data.paper_signal_config["gold_short_score_threshold"] == 35


def test_paper_trading_renderer_handles_missing_no_trade_reasons(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(dashboard_app, "st", fake_st)

    legacy_data = SimpleNamespace(
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
        paper_recent_signal_reviews=[],
        paper_open_positions=[],
        paper_closed_positions=[],
        paper_recent_orders=[],
        paper_recent_risk_events=[],
        paper_recent_run_summaries=[],
        paper_journal_notes=[],
    )

    dashboard_app._render_paper_trading(legacy_data)

    assert "No no-trade reasons have been recorded yet." in fake_st.infos


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
                "paper_trading:",
                "  enabled: true",
                "  starting_equity: 10000",
                "paper_signal:",
                "  profile: balanced",
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


class _FakeStreamlit:
    def __init__(self) -> None:
        self.infos: list[str] = []

    def subheader(self, *_args, **_kwargs) -> None:
        return None

    def error(self, *_args, **_kwargs) -> None:
        return None

    def caption(self, *_args, **_kwargs) -> None:
        return None

    def markdown(self, *_args, **_kwargs) -> None:
        return None

    def info(self, value, *_args, **_kwargs) -> None:
        self.infos.append(str(value))

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

    def columns(self, count: int):
        return [_FakeColumn(self) for _ in range(count)]

    def metric(self, *_args, **_kwargs) -> None:
        return None
