from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import main as app
from core.config import load_config
from core.models import DeliveryResult, WorkflowOutcome


def test_main_paper_run_persists_normalized_signal_reviews(monkeypatch, tmp_path: Path, capsys) -> None:
    _write_config(tmp_path)
    config = load_config(tmp_path)

    class FakeOrchestrator:
        def __init__(self, database_path: Path) -> None:
            self.database_path = database_path

        def run_daily_brief(self) -> WorkflowOutcome:
            with closing(sqlite3.connect(self.database_path)) as connection, connection:
                connection.execute(
                    """
                    INSERT INTO workflow_runs (id, run_date, mode, status, summary, report_text)
                    VALUES (1, '2026-06-01', 'research', 'COMPLETED', 'ok', 'daily brief')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO risk_snapshots (
                        workflow_run_id, status, trade_permission, data_quality,
                        daily_loss_pct, weekly_loss_pct, notes_json
                    )
                    VALUES (1, 'OK', 'WATCH ONLY', 'OK', 0.0, 0.0, '[]')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO market_snapshots (
                        workflow_run_id, timestamp, asset, source, data_type, value_json, status, error_summary
                    )
                    VALUES (1, '2026-06-01T00:00:00+00:00', 'BTC', 'test', 'price', ?, 'OK', NULL)
                    """,
                    (json.dumps({"price": 100.0}),),
                )
                connection.executemany(
                    """
                    INSERT INTO score_snapshots (
                        workflow_run_id, timestamp, asset, total_score, bias, confidence,
                        data_completeness, components_json, reasons_json, warnings_json
                    )
                    VALUES (?, '2026-06-01T00:00:00+00:00', ?, ?, ?, ?, ?, '[]', '[]', '[]')
                    """,
                    [
                        (1, "BTC", 74, "Bullish", "Medium", 95),
                        (1, "Gold", 52, "Neutral", "Low", 45),
                    ],
                )

            return WorkflowOutcome(
                workflow_run_id=1,
                report_text="daily brief",
                delivery=DeliveryResult(success=True, status="DRY_RUN", recipient="local-log"),
            )

    monkeypatch.setattr(app, "load_config", lambda project_root: config)
    monkeypatch.setattr(app, "setup_logging", lambda cfg: None)
    monkeypatch.setattr(app, "build_orchestrator", lambda cfg, runtime: FakeOrchestrator(config.database_path))

    exit_code = app.main(["--dry-run", "--paper-run"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "daily brief" in output
    assert "Paper Trading Run" in output
    assert "Signals Evaluated: 2" in output
    assert "Signals Accepted: 1" in output
    assert "No-Trade Signals: 1" in output
    assert "Active Profile: conservative" in output

    with closing(sqlite3.connect(config.database_path)) as connection:
        review_rows = connection.execute(
            """
            SELECT asset, review_status, signal_action, reasons_json
            FROM paper_signal_reviews
            ORDER BY id ASC
            """
        ).fetchall()
        run_summary = connection.execute(
            """
            SELECT active_profile, signals_evaluated, signals_accepted, signals_rejected, no_trade_count
            FROM paper_run_summaries
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert len(review_rows) == 2
    assert {(row[0], row[1]) for row in review_rows} == {("BTC", "ACCEPTED"), ("Gold", "NO_TRADE")}
    assert any("SIGNAL_ACCEPTED" in row[3] for row in review_rows)
    assert run_summary == ("conservative", 2, 1, 0, 1)


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "\n".join(
            [
                "app:",
                "  name: AI Trading Firm",
                "  mode: research",
                "  timezone: Asia/Bangkok",
                "database:",
                "  path: data/database.db",
                "logging:",
                "  level: INFO",
                "  file_path: data/logs/test.log",
                "telegram:",
                "  timeout_seconds: 10",
                "  dry_run_if_missing_credentials: true",
                "market_data:",
                "  timeout_seconds: 10",
                "  btc_public_price_url: https://api.binance.com/api/v3/ticker/price",
                "  fear_and_greed_url: https://api.alternative.me/fng/",
                "btc_derivatives:",
                "  symbol: BTCUSDT",
                "  funding_rate_url: https://fapi.binance.com/fapi/v1/premiumIndex",
                "  open_interest_url: https://fapi.binance.com/fapi/v1/openInterest",
                "fred:",
                "  base_url: https://api.stlouisfed.org/fred/series/observations",
                "  timeout_seconds: 10",
                "  series:",
                "    gold_us10y:",
                "      series_id: DGS10",
                "      data_type: us10y",
                "      display_name: US10Y",
                "      stale_after_days: 10",
                "risk:",
                "  max_daily_loss_pct: 1.0",
                "  max_weekly_loss_pct: 3.0",
                "  execution_enabled: false",
                "paper_trading:",
                "  enabled: true",
                "  starting_equity: 10000",
                "  base_currency: USD",
                "  max_risk_per_trade_pct: 0.25",
                "  max_daily_loss_pct: 1.0",
                "  max_open_positions: 2",
                "  allow_long: true",
                "  allow_short: true",
                "  fill_mode: close_price",
                "paper_signal:",
                "  profile: conservative",
                "  btc_long_score_threshold: 70",
                "  btc_short_score_threshold: 35",
                "  gold_long_score_threshold: 70",
                "  gold_short_score_threshold: 35",
                "  min_confidence: Medium",
                "  min_btc_data_completeness: 80",
                "  min_gold_data_completeness: 60",
                "  allow_neutral_bias: false",
                "  exploratory_mode: false",
            ]
        ),
        encoding="utf-8",
    )
