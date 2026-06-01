from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

logger = logging.getLogger(__name__)


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS workflow_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT,
    report_text TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS bot_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id INTEGER NOT NULL,
    bot_name TEXT NOT NULL,
    asset TEXT NOT NULL,
    score INTEGER NOT NULL,
    bias TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id)
);

CREATE TABLE IF NOT EXISTS risk_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    trade_permission TEXT NOT NULL,
    data_quality TEXT NOT NULL,
    daily_loss_pct REAL NOT NULL,
    weekly_loss_pct REAL NOT NULL,
    notes_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id)
);

CREATE TABLE IF NOT EXISTS outbound_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    recipient TEXT NOT NULL,
    message_preview TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id)
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    asset TEXT NOT NULL,
    source TEXT NOT NULL,
    data_type TEXT NOT NULL,
    value_json TEXT,
    status TEXT NOT NULL,
    error_summary TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id)
);

CREATE TABLE IF NOT EXISTS score_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    asset TEXT NOT NULL,
    total_score INTEGER NOT NULL,
    bias TEXT NOT NULL,
    confidence TEXT NOT NULL,
    data_completeness INTEGER NOT NULL,
    components_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id)
);

CREATE TABLE IF NOT EXISTS paper_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    asset TEXT NOT NULL,
    direction TEXT NOT NULL,
    order_type TEXT NOT NULL,
    status TEXT NOT NULL,
    signal_source TEXT NOT NULL,
    intended_entry REAL,
    stop_loss REAL,
    take_profit REAL,
    risk_pct REAL,
    size REAL,
    reason_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    rejection_reason TEXT,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id)
);

CREATE TABLE IF NOT EXISTS paper_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    workflow_run_id INTEGER,
    opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT,
    asset TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    stop_loss REAL,
    take_profit REAL,
    size REAL NOT NULL,
    status TEXT NOT NULL,
    pnl_abs REAL NOT NULL DEFAULT 0,
    pnl_pct REAL NOT NULL DEFAULT 0,
    reason_json TEXT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES paper_orders (id),
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id)
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    position_id INTEGER,
    workflow_run_id INTEGER,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    asset TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    size REAL NOT NULL,
    pnl_abs REAL NOT NULL,
    pnl_pct REAL NOT NULL,
    result_status TEXT NOT NULL,
    reason_json TEXT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES paper_orders (id),
    FOREIGN KEY (position_id) REFERENCES paper_positions (id),
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id)
);

CREATE TABLE IF NOT EXISTS paper_equity_curve (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    equity REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    drawdown_pct REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id INTEGER,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    asset TEXT,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    details_json TEXT NOT NULL,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id)
);

CREATE TABLE IF NOT EXISTS paper_signal_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    asset TEXT NOT NULL,
    signal_action TEXT NOT NULL,
    review_status TEXT NOT NULL,
    bias TEXT NOT NULL,
    total_score INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    data_completeness INTEGER NOT NULL,
    active_profile TEXT NOT NULL,
    signal_source TEXT,
    reasons_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id)
);

CREATE TABLE IF NOT EXISTS paper_run_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id INTEGER NOT NULL,
    run_timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL,
    active_profile TEXT NOT NULL DEFAULT 'conservative',
    signals_evaluated INTEGER NOT NULL,
    signals_accepted INTEGER NOT NULL DEFAULT 0,
    signals_rejected INTEGER NOT NULL DEFAULT 0,
    no_trade_count INTEGER NOT NULL DEFAULT 0,
    orders_opened INTEGER NOT NULL,
    positions_updated INTEGER NOT NULL,
    equity_snapshot_id INTEGER,
    notes_json TEXT NOT NULL,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id),
    FOREIGN KEY (equity_snapshot_id) REFERENCES paper_equity_curve (id)
);

CREATE TABLE IF NOT EXISTS paper_journal_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    note_type TEXT NOT NULL,
    reference_id TEXT,
    asset TEXT,
    profile TEXT,
    title TEXT,
    note_text TEXT NOT NULL,
    tags TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS research_readiness_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_run_id INTEGER NOT NULL,
    asset TEXT NOT NULL,
    readiness_score INTEGER NOT NULL,
    regime TEXT NOT NULL,
    data_completeness INTEGER NOT NULL,
    decision_ready INTEGER NOT NULL,
    stale_sources_json TEXT NOT NULL,
    missing_sources_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    no_trade_reasons_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs (id)
);
"""


def initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.executescript(SCHEMA)
        _run_schema_migrations(connection)

    logger.info("SQLite database initialized at %s.", database_path)


def _run_schema_migrations(connection: sqlite3.Connection) -> None:
    _ensure_column(
        connection,
        table_name="paper_run_summaries",
        column_name="active_profile",
        column_definition="TEXT NOT NULL DEFAULT 'conservative'",
    )


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    if not _table_exists(connection, table_name):
        return
    existing_columns = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return
    connection.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None
