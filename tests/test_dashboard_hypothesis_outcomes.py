from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import dashboard.app as dashboard_app
from dashboard.data_loader import load_dashboard_data
from database.init_db import initialize_database


def test_dashboard_loader_handles_missing_hypothesis_outcome_table(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("DROP TABLE strategy_hypothesis_outcomes")

    data = load_dashboard_data(tmp_path)

    assert data.hypothesis_outcomes_enabled is True
    assert data.latest_hypothesis_outcomes == []
    assert data.recent_hypothesis_outcomes == []
    assert data.hypothesis_outcome_summary["total_evaluated"] == 0


def test_dashboard_loader_reads_latest_hypothesis_outcomes(tmp_path: Path) -> None:
    _write_config(tmp_path)
    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (id, run_date, mode, status)
            VALUES (1, '2026-06-02', 'research', 'COMPLETED')
            """
        )
        connection.execute(
            """
            INSERT INTO strategy_hypotheses (
                id, workflow_run_id, asset, hypothesis_name, direction_bias, regime, readiness_score, score,
                confidence, data_completeness, hypothesis_status, suggested_strategy_family,
                suggested_holding_period, reasons_json, blockers_json, warnings_json, invalidation_notes, created_at
            )
            VALUES (
                1, 1, 'BTC', 'BTC Test Hypothesis', 'LONG', 'TREND_UP', 80, 65, 'High', 100, 'ACTIVE',
                'BTC_TREND_CONTINUATION', '1-5 days', '[]', '[]', '[]', 'Invalidate later.',
                '2026-06-01T00:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO strategy_hypothesis_outcomes (
                hypothesis_id, workflow_run_id, asset, hypothesis_name, direction_bias, strategy_family,
                horizon_hours, created_at, evaluated_at, entry_reference_price, followup_price, move_pct,
                max_favorable_move_pct, max_adverse_move_pct, outcome_status, reason, warnings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                "BTC",
                "BTC Test Hypothesis",
                "LONG",
                "BTC_TREND_CONTINUATION",
                24,
                "2026-06-01T00:00:00+00:00",
                "2026-06-02T00:00:00+00:00",
                100.0,
                101.0,
                1.0,
                1.2,
                0.3,
                "FAVORABLE",
                "LONG hypothesis moved favorably.",
                json.dumps([]),
            ),
        )

    data = load_dashboard_data(tmp_path)

    assert data.latest_hypothesis_outcomes[0]["asset"] == "BTC"
    assert data.latest_hypothesis_outcomes[0]["outcome_status"] == "FAVORABLE"
    assert data.hypothesis_outcome_summary["favorable_count"] == 1


def test_strategy_hypothesis_renderer_handles_missing_outcome_fields(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(dashboard_app, "st", fake_st)

    legacy_data = SimpleNamespace(
        strategy_hypotheses_enabled=True,
        latest_strategy_hypotheses=[
            {
                "asset": "BTC",
                "hypothesis_name": "BTC Test Hypothesis",
                "direction_bias": "LONG",
                "regime": "TREND_UP",
                "readiness_score": 80,
                "score": 65,
                "confidence": "High",
                "data_completeness": 100,
                "hypothesis_status": "ACTIVE",
                "suggested_strategy_family": "BTC_TREND_CONTINUATION",
                "suggested_holding_period": "1-5 days",
                "reasons": ["Reason"],
                "blockers": [],
                "warnings": [],
                "invalidation_notes": "Invalidate later.",
                "created_at": "2026-06-01T00:00:00+00:00",
            }
        ],
        recent_strategy_hypotheses=[],
    )

    dashboard_app._render_strategy_hypotheses(
        legacy_data,
        {"asset": None, "data_type": None, "start_date": None, "end_date": None, "limit": 25},
    )

    assert "Hypothesis outcomes are disabled in config." in fake_st.infos


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
                "strategy_hypotheses:",
                "  enabled: true",
                "  min_readiness_score: 70",
                "  min_confidence: Medium",
                "  allow_watch_when_not_ready: true",
                "hypothesis_outcomes:",
                "  enabled: true",
                "  horizons_hours: [4, 24, 72]",
                "  neutral_move_pct:",
                "    BTC: 0.25",
                "    Gold: 0.20",
                "  max_lookback_days: 14",
            ]
        ),
        encoding="utf-8",
    )


class _FakeColumn:
    def __init__(self, streamlit: "_FakeStreamlit") -> None:
        self._streamlit = streamlit

    def metric(self, *args, **kwargs) -> None:
        self._streamlit.metric(*args, **kwargs)


class _FakeStreamlit:
    def __init__(self) -> None:
        self.infos: list[str] = []

    def subheader(self, *_args, **_kwargs) -> None:
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

    def columns(self, count: int):
        return [_FakeColumn(self) for _ in range(count)]

    def metric(self, *_args, **_kwargs) -> None:
        return None
