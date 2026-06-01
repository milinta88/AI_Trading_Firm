from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

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
