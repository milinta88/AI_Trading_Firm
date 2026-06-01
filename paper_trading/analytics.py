from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PaperPerformanceMetrics:
    starting_equity: float
    latest_equity: float
    total_pnl_abs: float
    total_pnl_pct: float
    max_drawdown_pct: float
    total_orders: int
    open_positions: int
    closed_positions: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    profit_factor: float | None
    average_pnl: float
    average_r_multiple: float | None


@dataclass(frozen=True)
class PaperSignalReviewAnalytics:
    signals_evaluated: int
    signals_accepted: int
    signals_rejected: int
    no_trade_count: int
    accepted_by_asset: dict[str, int] = field(default_factory=dict)
    rejected_by_asset: dict[str, int] = field(default_factory=dict)
    no_trade_by_asset: dict[str, int] = field(default_factory=dict)
    rejected_by_reason: dict[str, int] = field(default_factory=dict)
    no_trade_by_reason: dict[str, int] = field(default_factory=dict)
    accepted_by_profile: dict[str, int] = field(default_factory=dict)
    no_trade_by_profile: dict[str, int] = field(default_factory=dict)
    active_profile: str | None = None
    source_mode: str = "none"
    legacy_signal_events_ignored: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PaperAnalyticsReport:
    database_available: bool
    message: str
    performance: PaperPerformanceMetrics
    signal_review: PaperSignalReviewAnalytics
    latest_run_summary: dict[str, Any] | None = None
    recent_run_summaries: list[dict[str, Any]] = field(default_factory=list)
    pnl_by_asset: list[dict[str, Any]] = field(default_factory=list)
    rejection_reasons: list[dict[str, Any]] = field(default_factory=list)
    no_trade_reasons: list[dict[str, Any]] = field(default_factory=list)
    recent_closed_positions: list[dict[str, Any]] = field(default_factory=list)
    recent_signal_reviews: list[dict[str, Any]] = field(default_factory=list)


class PaperAnalytics:
    """Read-only analytics over local paper-trading SQLite tables."""

    def __init__(self, database_path: Path, starting_equity: float) -> None:
        self.database_path = database_path
        self.starting_equity = starting_equity

    def build_report(self, limit: int = 25) -> PaperAnalyticsReport:
        if not self.database_path.exists():
            return self._empty_report(f"Database not found at {self.database_path}.")

        try:
            with closing(self._connect_read_only()) as connection:
                performance = self._build_performance(connection)
                signal_review = self._build_signal_review(connection)
                latest_run_summary_row = self._fetch_one(
                    connection,
                    "SELECT * FROM paper_run_summaries ORDER BY id DESC LIMIT 1",
                ) if _table_exists(connection, "paper_run_summaries") else None
                recent_run_summary_rows = self._fetch_all(
                    connection,
                    "SELECT * FROM paper_run_summaries ORDER BY id DESC LIMIT ?",
                    (limit,),
                ) if _table_exists(connection, "paper_run_summaries") else []
                pnl_by_asset = self._build_pnl_by_asset(connection)
                recent_closed_position_rows = self._fetch_all(
                    connection,
                    "SELECT * FROM paper_positions WHERE status != 'OPEN' ORDER BY id DESC LIMIT ?",
                    (limit,),
                ) if _table_exists(connection, "paper_positions") else []
                recent_signal_review_rows = self._fetch_all(
                    connection,
                    "SELECT * FROM paper_signal_reviews ORDER BY id DESC LIMIT ?",
                    (limit,),
                ) if _table_exists(connection, "paper_signal_reviews") else []
        except sqlite3.Error as exc:
            return self._empty_report(f"Unable to read paper analytics: {exc}")

        latest_run_summary = self._normalize_run_summary(latest_run_summary_row)
        recent_run_summaries = [
            normalized
            for row in recent_run_summary_rows
            if (normalized := self._normalize_run_summary(row)) is not None
        ]
        recent_closed_positions = [
            self._normalize_closed_position(row)
            for row in recent_closed_position_rows
        ]
        recent_signal_reviews = [
            self._normalize_signal_review(row)
            for row in recent_signal_review_rows
        ]

        return PaperAnalyticsReport(
            database_available=True,
            message=f"Loaded paper analytics from {self.database_path}.",
            performance=performance,
            signal_review=signal_review,
            latest_run_summary=latest_run_summary,
            recent_run_summaries=recent_run_summaries,
            pnl_by_asset=pnl_by_asset,
            rejection_reasons=_count_rows(signal_review.rejected_by_reason, "reason", "rejection_count"),
            no_trade_reasons=_count_rows(signal_review.no_trade_by_reason, "reason", "no_trade_count"),
            recent_closed_positions=recent_closed_positions,
            recent_signal_reviews=recent_signal_reviews,
        )

    def _build_performance(self, connection: sqlite3.Connection) -> PaperPerformanceMetrics:
        latest_equity = self._scalar_float(
            connection,
            "SELECT equity FROM paper_equity_curve ORDER BY id DESC LIMIT 1",
            default=self.starting_equity,
        ) if _table_exists(connection, "paper_equity_curve") else self.starting_equity
        total_pnl_abs = latest_equity - self.starting_equity
        total_pnl_pct = (total_pnl_abs / self.starting_equity * 100) if self.starting_equity else 0.0
        max_drawdown_pct = self._scalar_float(
            connection,
            "SELECT MAX(drawdown_pct) FROM paper_equity_curve",
            default=0.0,
        ) if _table_exists(connection, "paper_equity_curve") else 0.0

        total_orders = self._count(connection, "paper_orders")
        open_positions = self._count_where(connection, "paper_positions", "status = 'OPEN'")
        closed_positions = self._count_where(connection, "paper_positions", "status != 'OPEN'")
        total_trades = self._count(connection, "paper_trades")
        winning_trades = self._count_where(connection, "paper_trades", "pnl_abs > 0")
        losing_trades = self._count_where(connection, "paper_trades", "pnl_abs < 0")
        gross_profit = self._scalar_float(
            connection,
            "SELECT SUM(pnl_abs) FROM paper_trades WHERE pnl_abs > 0",
            default=0.0,
        )
        gross_loss_abs = abs(
            self._scalar_float(
                connection,
                "SELECT SUM(pnl_abs) FROM paper_trades WHERE pnl_abs < 0",
                default=0.0,
            )
        )
        win_rate = (winning_trades / total_trades * 100) if total_trades else 0.0
        profit_factor = None
        if gross_loss_abs > 0:
            profit_factor = gross_profit / gross_loss_abs
        average_pnl = self._scalar_float(
            connection,
            "SELECT AVG(pnl_abs) FROM paper_trades",
            default=0.0,
        )
        average_r_multiple = self._average_r_multiple(connection)

        return PaperPerformanceMetrics(
            starting_equity=self.starting_equity,
            latest_equity=latest_equity,
            total_pnl_abs=total_pnl_abs,
            total_pnl_pct=total_pnl_pct,
            max_drawdown_pct=max_drawdown_pct,
            total_orders=total_orders,
            open_positions=open_positions,
            closed_positions=closed_positions,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss_abs,
            profit_factor=profit_factor,
            average_pnl=average_pnl,
            average_r_multiple=average_r_multiple,
        )

    def _build_signal_review(self, connection: sqlite3.Connection) -> PaperSignalReviewAnalytics:
        if _table_exists(connection, "paper_signal_reviews"):
            rows = self._fetch_all(
                connection,
                "SELECT * FROM paper_signal_reviews ORDER BY id DESC",
            )
            if rows:
                return self._build_normalized_signal_review(connection, rows)

        if _table_exists(connection, "paper_risk_events"):
            return self._build_legacy_signal_review(connection)

        return PaperSignalReviewAnalytics(0, 0, 0, 0)

    def _build_normalized_signal_review(
        self,
        connection: sqlite3.Connection,
        rows: list[dict[str, Any]],
    ) -> PaperSignalReviewAnalytics:
        accepted_by_asset: dict[str, int] = {}
        rejected_by_asset: dict[str, int] = {}
        no_trade_by_asset: dict[str, int] = {}
        rejected_by_reason: dict[str, int] = {}
        no_trade_by_reason: dict[str, int] = {}
        accepted_by_profile: dict[str, int] = {}
        no_trade_by_profile: dict[str, int] = {}
        signals_accepted = 0
        signals_rejected = 0
        no_trade_count = 0

        for row in rows:
            status = str(row.get("review_status") or "")
            asset = str(row.get("asset") or "UNKNOWN")
            profile = str(row.get("active_profile") or "unknown")
            reason_codes = _reason_codes(row.get("reasons_json"))

            if status == "ACCEPTED":
                signals_accepted += 1
                accepted_by_asset[asset] = accepted_by_asset.get(asset, 0) + 1
                accepted_by_profile[profile] = accepted_by_profile.get(profile, 0) + 1
            elif status == "REJECTED":
                signals_rejected += 1
                rejected_by_asset[asset] = rejected_by_asset.get(asset, 0) + 1
                for code in reason_codes or ["RISK_REJECTED"]:
                    rejected_by_reason[code] = rejected_by_reason.get(code, 0) + 1
            elif status == "NO_TRADE":
                no_trade_count += 1
                no_trade_by_asset[asset] = no_trade_by_asset.get(asset, 0) + 1
                no_trade_by_profile[profile] = no_trade_by_profile.get(profile, 0) + 1
                for code in reason_codes or ["NO_TRADE"]:
                    no_trade_by_reason[code] = no_trade_by_reason.get(code, 0) + 1

        legacy_events_ignored = 0
        notes = [
            f"Using normalized paper_signal_reviews for signal analytics ({len(rows)} review rows).",
            "Reason counts are per reason occurrence; a single normalized review can contribute multiple reason codes.",
        ]
        if _table_exists(connection, "paper_risk_events"):
            legacy_events_ignored = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM paper_risk_events
                    WHERE event_type = 'PAPER_SIGNAL_RISK_CHECK'
                    """
                ).fetchone()[0]
            )
            if legacy_events_ignored:
                notes.append(
                    f"Ignoring {legacy_events_ignored} legacy PAPER_SIGNAL_RISK_CHECK events to avoid double-counting."
                )

        return PaperSignalReviewAnalytics(
            signals_evaluated=len(rows),
            signals_accepted=signals_accepted,
            signals_rejected=signals_rejected,
            no_trade_count=no_trade_count,
            accepted_by_asset=accepted_by_asset,
            rejected_by_asset=rejected_by_asset,
            no_trade_by_asset=no_trade_by_asset,
            rejected_by_reason=rejected_by_reason,
            no_trade_by_reason=no_trade_by_reason,
            accepted_by_profile=accepted_by_profile,
            no_trade_by_profile=no_trade_by_profile,
            active_profile=str(rows[0].get("active_profile")) if rows else None,
            source_mode="normalized",
            legacy_signal_events_ignored=legacy_events_ignored,
            notes=notes,
        )

    def _build_legacy_signal_review(self, connection: sqlite3.Connection) -> PaperSignalReviewAnalytics:
        rows = self._fetch_all(
            connection,
            """
            SELECT asset, status, reason, details_json
            FROM paper_risk_events
            WHERE event_type = 'PAPER_SIGNAL_RISK_CHECK'
            ORDER BY id DESC
            """,
        )
        rejected_by_reason: dict[str, int] = {}
        rejected_by_asset: dict[str, int] = {}
        no_trade_by_reason: dict[str, int] = {}
        no_trade_by_asset: dict[str, int] = {}
        accepted_by_asset: dict[str, int] = {}
        signals_accepted = 0
        signals_rejected = 0
        no_trade_count = 0

        for row in rows:
            status = str(row.get("status", ""))
            reason = str(row.get("reason") or "UNKNOWN")
            details = _parse_json_dict(row.get("details_json"))
            asset = str(row.get("asset") or "UNKNOWN")
            if status == "APPROVED":
                signals_accepted += 1
                accepted_by_asset[asset] = accepted_by_asset.get(asset, 0) + 1
            elif status == "REJECTED":
                signals_rejected += 1
                rejected_by_reason[reason] = rejected_by_reason.get(reason, 0) + 1
                rejected_by_asset[asset] = rejected_by_asset.get(asset, 0) + 1
            elif status == "SKIPPED" and str(details.get("review_category", "")).upper() == "NO_TRADE":
                no_trade_count += 1
                no_trade_by_reason[reason] = no_trade_by_reason.get(reason, 0) + 1
                no_trade_by_asset[asset] = no_trade_by_asset.get(asset, 0) + 1

        notes = [
            "Using legacy PAPER_SIGNAL_RISK_CHECK events because normalized paper_signal_reviews are not available yet.",
        ]
        return PaperSignalReviewAnalytics(
            signals_evaluated=len(rows),
            signals_accepted=signals_accepted,
            signals_rejected=signals_rejected,
            no_trade_count=no_trade_count,
            accepted_by_asset=accepted_by_asset,
            rejected_by_asset=rejected_by_asset,
            no_trade_by_asset=no_trade_by_asset,
            rejected_by_reason=rejected_by_reason,
            no_trade_by_reason=no_trade_by_reason,
            source_mode="legacy",
            notes=notes,
        )

    def _build_pnl_by_asset(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        if not _table_exists(connection, "paper_trades"):
            return []
        rows = connection.execute(
            """
            SELECT asset, COUNT(*) AS trade_count, SUM(pnl_abs) AS total_pnl
            FROM paper_trades
            GROUP BY asset
            ORDER BY asset
            """
        ).fetchall()
        return [
            {
                "asset": row["asset"],
                "trade_count": int(row["trade_count"]),
                "total_pnl": float(row["total_pnl"]) if row["total_pnl"] is not None else 0.0,
            }
            for row in rows
        ]

    def _average_r_multiple(self, connection: sqlite3.Connection) -> float | None:
        if not (_table_exists(connection, "paper_trades") and _table_exists(connection, "paper_positions")):
            return None
        rows = connection.execute(
            """
            SELECT
                t.pnl_abs,
                p.entry_price,
                p.stop_loss,
                p.size
            FROM paper_trades t
            JOIN paper_positions p ON p.id = t.position_id
            """
        ).fetchall()
        multiples: list[float] = []
        for row in rows:
            stop_loss = row["stop_loss"]
            if stop_loss is None or row["size"] in {None, 0}:
                continue
            risk_per_unit = abs(float(row["entry_price"]) - float(stop_loss))
            if risk_per_unit <= 0:
                continue
            risk_amount = risk_per_unit * float(row["size"])
            if risk_amount <= 0:
                continue
            multiples.append(float(row["pnl_abs"]) / risk_amount)
        if not multiples:
            return None
        return sum(multiples) / len(multiples)

    def _normalize_run_summary(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        normalized = dict(row)
        normalized["notes"] = _parse_json_list(normalized.get("notes_json"))
        return normalized

    def _normalize_closed_position(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        normalized["reasons"] = _parse_json_list(normalized.get("reason_json"))
        return normalized

    def _normalize_signal_review(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        normalized["reasons"] = _parse_json_reason_list(normalized.get("reasons_json"))
        normalized["warnings"] = _parse_json_list(normalized.get("warnings_json"))
        return normalized

    def _scalar_float(self, connection: sqlite3.Connection, query: str, default: float) -> float:
        row = connection.execute(query).fetchone()
        if row is None:
            return default
        value = row[0]
        return float(value) if value is not None else default

    def _count(self, connection: sqlite3.Connection, table_name: str) -> int:
        if not _table_exists(connection, table_name):
            return 0
        return int(connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])

    def _count_where(self, connection: sqlite3.Connection, table_name: str, predicate: str) -> int:
        if not _table_exists(connection, table_name):
            return 0
        return int(connection.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {predicate}").fetchone()[0])

    def _fetch_all(
        self,
        connection: sqlite3.Connection,
        query: str,
        params: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        return [dict(row) for row in connection.execute(query, params).fetchall()]

    def _fetch_one(
        self,
        connection: sqlite3.Connection,
        query: str,
        params: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        row = connection.execute(query, params).fetchone()
        return dict(row) if row else None

    def _connect_read_only(self) -> sqlite3.Connection:
        uri = f"{self.database_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _empty_report(self, message: str) -> PaperAnalyticsReport:
        return PaperAnalyticsReport(
            database_available=False,
            message=message,
            performance=PaperPerformanceMetrics(
                starting_equity=self.starting_equity,
                latest_equity=self.starting_equity,
                total_pnl_abs=0.0,
                total_pnl_pct=0.0,
                max_drawdown_pct=0.0,
                total_orders=0,
                open_positions=0,
                closed_positions=0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                gross_profit=0.0,
                gross_loss=0.0,
                profit_factor=None,
                average_pnl=0.0,
                average_r_multiple=None,
            ),
            signal_review=PaperSignalReviewAnalytics(0, 0, 0, 0),
        )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _parse_json_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _parse_json_reason_list(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            normalized.append(
                {
                    "code": str(item.get("code", "UNKNOWN")),
                    "message": str(item.get("message", "")),
                }
            )
        else:
            normalized.append({"code": str(item), "message": str(item)})
    return normalized


def _reason_codes(value: Any) -> list[str]:
    codes = {
        str(item.get("code") or "UNKNOWN")
        for item in _parse_json_reason_list(value)
    }
    return sorted(codes)


def _count_rows(counts: dict[str, int], key_name: str, value_name: str) -> list[dict[str, Any]]:
    return [
        {
            key_name: key,
            value_name: value,
        }
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
