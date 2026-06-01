from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from paper_trading.models import PaperOrder, PaperPosition, PaperRunSummary, PaperSignalReview


class PaperTradingRepository:
    """SQLite persistence for simulated-only paper trading state."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def fetch_latest_score_snapshots(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "score_snapshots"):
                return []
            rows = connection.execute("SELECT * FROM score_snapshots ORDER BY id DESC").fetchall()

        latest_by_asset: dict[str, dict[str, Any]] = {}
        for row in rows:
            asset = str(row["asset"])
            if asset not in latest_by_asset:
                latest_by_asset[asset] = dict(row)
        return list(latest_by_asset.values())

    def fetch_latest_market_price(self, asset: str) -> float | None:
        data_type = "price" if asset == "BTC" else "gold_spot_price"
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "market_snapshots"):
                return None
            row = connection.execute(
                """
                SELECT value_json
                FROM market_snapshots
                WHERE asset = ? AND data_type = ? AND status = 'OK' AND value_json IS NOT NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (asset, data_type),
            ).fetchone()
        if not row:
            return None
        return _extract_price(row["value_json"])

    def fetch_latest_data_quality(self) -> str:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "risk_snapshots"):
                return "NOT_AVAILABLE"
            row = connection.execute(
                "SELECT data_quality FROM risk_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return str(row["data_quality"]) if row and row["data_quality"] else "NOT_AVAILABLE"

    def count_open_positions(self) -> int:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_positions"):
                return 0
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM paper_positions WHERE status = 'OPEN'"
                ).fetchone()[0]
            )

    def fetch_open_positions(self) -> list[PaperPosition]:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_positions"):
                return []
            rows = connection.execute(
                "SELECT * FROM paper_positions WHERE status = 'OPEN' ORDER BY id ASC"
            ).fetchall()
        return [_position_from_row(row) for row in rows]

    def fetch_open_position_rows(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_positions"):
                return []
            rows = connection.execute(
                "SELECT * FROM paper_positions WHERE status = 'OPEN' ORDER BY id DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_recent_order_rows(self, limit: int = 25) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_orders"):
                return []
            rows = connection.execute(
                "SELECT * FROM paper_orders ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_recent_risk_event_rows(self, limit: int = 25) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_risk_events"):
                return []
            rows = connection.execute(
                "SELECT * FROM paper_risk_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_recent_closed_position_rows(self, limit: int = 25) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_positions"):
                return []
            rows = connection.execute(
                "SELECT * FROM paper_positions WHERE status != 'OPEN' ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_recent_trade_rows(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_trades"):
                return []
            rows = connection.execute(
                "SELECT * FROM paper_trades ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_equity_curve_rows(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_equity_curve"):
                return []
            rows = connection.execute(
                "SELECT * FROM paper_equity_curve ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return list(reversed([dict(row) for row in rows]))

    def fetch_latest_run_summary_row(self) -> dict[str, Any] | None:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_run_summaries"):
                return None
            row = connection.execute(
                "SELECT * FROM paper_run_summaries ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def fetch_recent_run_summary_rows(self, limit: int = 25) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_run_summaries"):
                return []
            rows = connection.execute(
                "SELECT * FROM paper_run_summaries ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_recent_signal_review_rows(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_signal_reviews"):
                return []
            rows = connection.execute(
                "SELECT * FROM paper_signal_reviews ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_signal_review_rows_for_run(self, workflow_run_id: int) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_signal_reviews"):
                return []
            rows = connection.execute(
                """
                SELECT * FROM paper_signal_reviews
                WHERE workflow_run_id = ?
                ORDER BY id ASC
                """,
                (workflow_run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_equity(self, starting_equity: float) -> float:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_equity_curve"):
                return starting_equity
            row = connection.execute(
                "SELECT equity FROM paper_equity_curve ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return float(row["equity"]) if row and row["equity"] is not None else starting_equity

    def peak_equity(self, starting_equity: float) -> float:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_equity_curve"):
                return starting_equity
            row = connection.execute("SELECT MAX(equity) AS peak FROM paper_equity_curve").fetchone()
        peak = float(row["peak"]) if row and row["peak"] is not None else starting_equity
        return max(peak, starting_equity)

    def realized_pnl_total(self) -> float:
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_trades"):
                return 0.0
            row = connection.execute("SELECT SUM(pnl_abs) AS pnl FROM paper_trades").fetchone()
        return float(row["pnl"]) if row and row["pnl"] is not None else 0.0

    def realized_pnl_for_date(self, run_date: date) -> float:
        date_prefix = run_date.isoformat()
        with closing(self._connect()) as connection, connection:
            if not _table_exists(connection, "paper_trades"):
                return 0.0
            row = connection.execute(
                """
                SELECT SUM(pnl_abs) AS pnl
                FROM paper_trades
                WHERE timestamp LIKE ?
                """,
                (f"{date_prefix}%",),
            ).fetchone()
        return float(row["pnl"]) if row and row["pnl"] is not None else 0.0

    def store_order(self, workflow_run_id: int, order: PaperOrder) -> int:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO paper_orders (
                    workflow_run_id,
                    asset,
                    direction,
                    order_type,
                    status,
                    signal_source,
                    intended_entry,
                    stop_loss,
                    take_profit,
                    risk_pct,
                    size,
                    reason_json,
                    warnings_json,
                    rejection_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_run_id,
                    order.asset,
                    order.direction,
                    order.order_type,
                    order.status,
                    order.signal_source,
                    order.intended_entry,
                    order.stop_loss,
                    order.take_profit,
                    order.risk_pct,
                    order.size,
                    json.dumps(order.reasons),
                    json.dumps(order.warnings),
                    order.rejection_reason,
                ),
            )
            return int(cursor.lastrowid)

    def create_position(self, workflow_run_id: int, order_id: int, position: PaperPosition) -> int:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO paper_positions (
                    order_id,
                    workflow_run_id,
                    asset,
                    direction,
                    entry_price,
                    stop_loss,
                    take_profit,
                    size,
                    status,
                    pnl_abs,
                    pnl_pct,
                    reason_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    workflow_run_id,
                    position.asset,
                    position.direction,
                    position.entry_price,
                    position.stop_loss,
                    position.take_profit,
                    position.size,
                    position.status,
                    position.pnl_abs,
                    position.pnl_pct,
                    json.dumps(position.reasons),
                ),
            )
            return int(cursor.lastrowid)

    def close_position(
        self,
        workflow_run_id: int,
        position: PaperPosition,
        exit_price: float,
        status: str,
        reasons: list[str],
    ) -> tuple[int, float, float]:
        pnl_abs = calculate_position_pnl(position.direction, position.entry_price, exit_price, position.size)
        position_value = position.entry_price * position.size
        pnl_pct = (pnl_abs / position_value) * 100 if position_value else 0.0
        timestamp = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE paper_positions
                SET status = ?,
                    closed_at = ?,
                    exit_price = ?,
                    pnl_abs = ?,
                    pnl_pct = ?,
                    reason_json = ?
                WHERE id = ?
                """,
                (
                    status,
                    timestamp,
                    exit_price,
                    pnl_abs,
                    pnl_pct,
                    json.dumps([*position.reasons, *reasons]),
                    position.id,
                ),
            )
            cursor = connection.execute(
                """
                INSERT INTO paper_trades (
                    order_id,
                    position_id,
                    workflow_run_id,
                    timestamp,
                    asset,
                    direction,
                    entry_price,
                    exit_price,
                    size,
                    pnl_abs,
                    pnl_pct,
                    result_status,
                    reason_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position.order_id,
                    position.id,
                    workflow_run_id,
                    timestamp,
                    position.asset,
                    position.direction,
                    position.entry_price,
                    exit_price,
                    position.size,
                    pnl_abs,
                    pnl_pct,
                    status,
                    json.dumps(reasons),
                ),
            )
            return int(cursor.lastrowid), pnl_abs, pnl_pct

    def store_equity_curve(self, equity: float, realized_pnl: float, unrealized_pnl: float, drawdown_pct: float) -> int:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO paper_equity_curve (timestamp, equity, realized_pnl, unrealized_pnl, drawdown_pct)
                VALUES (?, ?, ?, ?, ?)
                """,
                (datetime.now(UTC).isoformat(), equity, realized_pnl, unrealized_pnl, drawdown_pct),
            )
            return int(cursor.lastrowid)

    def store_risk_event(
        self,
        workflow_run_id: int | None,
        asset: str | None,
        event_type: str,
        status: str,
        reason: str,
        details: dict[str, Any],
    ) -> int:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO paper_risk_events (
                    workflow_run_id, asset, event_type, status, reason, details_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (workflow_run_id, asset, event_type, status, reason, json.dumps(details)),
            )
            return int(cursor.lastrowid)

    def store_signal_review(self, review: PaperSignalReview) -> int:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO paper_signal_reviews (
                    workflow_run_id,
                    asset,
                    signal_action,
                    review_status,
                    bias,
                    total_score,
                    confidence,
                    data_completeness,
                    active_profile,
                    signal_source,
                    reasons_json,
                    warnings_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review.workflow_run_id,
                    review.asset,
                    review.signal_action,
                    review.review_status,
                    review.bias,
                    review.total_score,
                    review.confidence,
                    review.data_completeness,
                    review.active_profile,
                    review.signal_source,
                    json.dumps(review.reasons),
                    json.dumps(review.warnings),
                ),
            )
            return int(cursor.lastrowid)

    def store_run_summary(self, summary: PaperRunSummary) -> int:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO paper_run_summaries (
                    workflow_run_id,
                    status,
                    active_profile,
                    signals_evaluated,
                    signals_accepted,
                    signals_rejected,
                    no_trade_count,
                    orders_opened,
                    positions_updated,
                    equity_snapshot_id,
                    notes_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.workflow_run_id,
                    summary.status,
                    summary.active_profile,
                    summary.signals_evaluated,
                    summary.signals_accepted,
                    summary.signals_rejected,
                    summary.no_trade_count,
                    summary.orders_opened,
                    summary.positions_updated,
                    summary.equity_curve_id,
                    json.dumps(summary.notes),
                ),
            )
            return int(cursor.lastrowid)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection


def calculate_position_pnl(direction: str, entry_price: float, exit_price: float, size: float) -> float:
    if direction == "SHORT":
        return (entry_price - exit_price) * size
    return (exit_price - entry_price) * size


def unrealized_pnl_for_position(position: PaperPosition, latest_price: float | None) -> float:
    if latest_price is None:
        return 0.0
    return calculate_position_pnl(position.direction, position.entry_price, latest_price, position.size)


def _position_from_row(row: sqlite3.Row) -> PaperPosition:
    return PaperPosition(
        id=int(row["id"]),
        order_id=int(row["order_id"]) if row["order_id"] is not None else None,
        workflow_run_id=int(row["workflow_run_id"]) if row["workflow_run_id"] is not None else None,
        opened_at=row["opened_at"],
        closed_at=row["closed_at"],
        asset=row["asset"],
        direction=row["direction"],
        entry_price=float(row["entry_price"]),
        exit_price=float(row["exit_price"]) if row["exit_price"] is not None else None,
        stop_loss=float(row["stop_loss"]) if row["stop_loss"] is not None else None,
        take_profit=float(row["take_profit"]) if row["take_profit"] is not None else None,
        size=float(row["size"]),
        status=row["status"],
        pnl_abs=float(row["pnl_abs"]),
        pnl_pct=float(row["pnl_pct"]),
        reasons=_loads_list(row["reason_json"]),
    )


def _extract_price(value_json: str) -> float | None:
    try:
        payload = json.loads(value_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("price", "latest_value"):
        if key not in payload:
            continue
        try:
            return float(payload[key])
        except (TypeError, ValueError):
            return None
    return None


def _loads_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None
