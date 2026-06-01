from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from database.init_db import initialize_database
from paper_trading.analytics import PaperAnalytics


def test_paper_analytics_prefers_normalized_signal_reviews_without_double_counting(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
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
                (1, "BTC", "LONG", "ACCEPTED", "Bullish", 74, "Medium", 95, "balanced", "paper_signal_balanced", json.dumps([{"code": "SIGNAL_ACCEPTED", "message": "ok"}]), "[]"),
                (1, "BTC", "LONG", "REJECTED", "Bullish", 76, "Medium", 95, "balanced", "paper_signal_balanced", json.dumps([{"code": "RISK_REJECTED", "message": "max positions"}]), "[]"),
                (1, "Gold", "NO_TRADE", "NO_TRADE", "Neutral", 52, "Low", 55, "balanced", "paper_signal_balanced", json.dumps([{"code": "CONFIDENCE_TOO_LOW", "message": "low confidence"}]), "[]"),
                (1, "Gold", "NO_TRADE", "NO_TRADE", "Neutral", 49, "Low", 45, "balanced", "paper_signal_balanced", json.dumps([{"code": "DATA_COMPLETENESS_TOO_LOW", "message": "insufficient completeness"}]), "[]"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO paper_risk_events (workflow_run_id, asset, event_type, status, reason, details_json)
            VALUES (?, ?, 'PAPER_SIGNAL_RISK_CHECK', ?, ?, ?)
            """,
            [
                (1, "BTC", "APPROVED", "legacy approved", json.dumps({"review_category": "APPROVED"})),
                (1, "BTC", "REJECTED", "legacy rejected", json.dumps({"review_category": "REJECTED"})),
            ],
        )

    report = PaperAnalytics(database_path=database_path, starting_equity=10_000.0).build_report(limit=10)
    review = report.signal_review

    assert review.source_mode == "normalized"
    assert review.signals_evaluated == 4
    assert review.signals_evaluated == review.signals_accepted + review.signals_rejected + review.no_trade_count
    assert review.signals_accepted == 1
    assert review.signals_rejected == 1
    assert review.no_trade_count == 2
    assert review.accepted_by_asset == {"BTC": 1}
    assert review.rejected_by_asset == {"BTC": 1}
    assert review.no_trade_by_asset == {"Gold": 2}
    assert review.rejected_by_reason == {"RISK_REJECTED": 1}
    assert review.no_trade_by_reason == {
        "CONFIDENCE_TOO_LOW": 1,
        "DATA_COMPLETENESS_TOO_LOW": 1,
    }
    assert review.accepted_by_profile == {"balanced": 1}
    assert review.no_trade_by_profile == {"balanced": 2}
    assert review.legacy_signal_events_ignored == 2
    assert any("Ignoring 2 legacy PAPER_SIGNAL_RISK_CHECK events" in note for note in review.notes)
    assert report.rejection_reasons == [{"reason": "RISK_REJECTED", "rejection_count": 1}]
