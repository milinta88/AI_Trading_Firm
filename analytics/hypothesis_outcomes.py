from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.config import HypothesisOutcomeConfig
from core.models import HypothesisOutcome


@dataclass(frozen=True)
class _StoredHypothesis:
    hypothesis_id: int
    workflow_run_id: int
    asset: str
    hypothesis_name: str
    direction_bias: str
    hypothesis_status: str
    strategy_family: str
    created_at: datetime


@dataclass(frozen=True)
class _SnapshotPricePoint:
    timestamp: datetime
    price: float


class HypothesisOutcomeEvaluator:
    """Evaluates persisted strategy hypotheses against later persisted market snapshots."""

    def __init__(
        self,
        config: HypothesisOutcomeConfig,
        database_path: Path | None,
    ) -> None:
        self.config = config
        self.database_path = database_path

    def evaluate_pending(self, now: datetime | None = None) -> list[HypothesisOutcome]:
        if not self.config.enabled or not self.database_path or not self.database_path.exists():
            return []

        evaluation_time = now.astimezone(UTC) if now else datetime.now(UTC)
        cutoff = evaluation_time - timedelta(days=self.config.max_lookback_days)

        try:
            with self._connect_read_only() as connection:
                if not self._table_exists(connection, "strategy_hypotheses"):
                    return []
                if not self._table_exists(connection, "market_snapshots"):
                    return []

                hypotheses = self._fetch_hypotheses(connection, cutoff)
                existing_outcomes = self._fetch_existing_outcome_statuses(connection)

                outcomes: list[HypothesisOutcome] = []
                for hypothesis in hypotheses:
                    for horizon_hours in self.config.horizons_hours:
                        target_time = hypothesis.created_at + timedelta(hours=horizon_hours)
                        if evaluation_time < target_time:
                            continue

                        existing_status = existing_outcomes.get((hypothesis.hypothesis_id, horizon_hours))
                        if existing_status and existing_status != "INSUFFICIENT_FOLLOWUP_DATA":
                            continue

                        outcome = self._evaluate_hypothesis_horizon(
                            connection=connection,
                            hypothesis=hypothesis,
                            horizon_hours=horizon_hours,
                            evaluation_time=evaluation_time,
                        )
                        if (
                            existing_status == "INSUFFICIENT_FOLLOWUP_DATA"
                            and outcome.outcome_status == "INSUFFICIENT_FOLLOWUP_DATA"
                        ):
                            continue
                        outcomes.append(outcome)
                return outcomes
        except sqlite3.Error:
            return []

    def load_recent(self, limit: int = 25) -> list[HypothesisOutcome]:
        if not self.database_path or not self.database_path.exists():
            return []

        try:
            with self._connect_read_only() as connection:
                if not self._table_exists(connection, "strategy_hypothesis_outcomes"):
                    return []
                rows = connection.execute(
                    "SELECT * FROM strategy_hypothesis_outcomes ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        except sqlite3.Error:
            return []

        return [self._row_to_outcome(dict(row)) for row in rows]

    def _evaluate_hypothesis_horizon(
        self,
        *,
        connection: sqlite3.Connection,
        hypothesis: _StoredHypothesis,
        horizon_hours: int,
        evaluation_time: datetime,
    ) -> HypothesisOutcome:
        warnings: list[str] = []
        target_time = hypothesis.created_at + timedelta(hours=horizon_hours)
        entry_point = self._fetch_entry_reference_price(connection, hypothesis.asset, hypothesis.created_at, warnings)

        if hypothesis.hypothesis_status == "BLOCKED":
            return self._build_outcome(
                hypothesis=hypothesis,
                horizon_hours=horizon_hours,
                evaluated_at=evaluation_time,
                entry_point=entry_point,
                followup_point=None,
                outcome_status="BLOCKED_NOT_EVALUATED",
                reason="Hypothesis status is BLOCKED, so outcome tracking remains informational only.",
                warnings=warnings,
            )

        if hypothesis.direction_bias == "NO_TRADE":
            return self._build_outcome(
                hypothesis=hypothesis,
                horizon_hours=horizon_hours,
                evaluated_at=evaluation_time,
                entry_point=entry_point,
                followup_point=None,
                outcome_status="BLOCKED_NOT_EVALUATED",
                reason="Hypothesis direction is NO_TRADE, so it is not outcome-evaluated.",
                warnings=warnings,
            )

        followup_point = self._fetch_followup_price(connection, hypothesis.asset, target_time)
        if entry_point is None:
            return self._build_outcome(
                hypothesis=hypothesis,
                horizon_hours=horizon_hours,
                evaluated_at=evaluation_time,
                entry_point=None,
                followup_point=followup_point,
                outcome_status="INSUFFICIENT_FOLLOWUP_DATA",
                reason="No persisted entry reference price was available near hypothesis creation.",
                warnings=warnings,
            )

        if followup_point is None:
            return self._build_outcome(
                hypothesis=hypothesis,
                horizon_hours=horizon_hours,
                evaluated_at=evaluation_time,
                entry_point=entry_point,
                followup_point=None,
                outcome_status="INSUFFICIENT_FOLLOWUP_DATA",
                reason="No persisted follow-up price snapshot exists on or after the target horizon yet.",
                warnings=warnings,
            )

        move_pct = ((followup_point.price - entry_point.price) / entry_point.price) * 100.0
        threshold = self.config.neutral_move_pct.get(hypothesis.asset, 0.0)

        if hypothesis.direction_bias == "NEUTRAL":
            outcome_status = "NEUTRAL"
            reason = "Hypothesis direction is NEUTRAL, so later market movement is recorded as reference context only."
        else:
            directional_move = move_pct if hypothesis.direction_bias == "LONG" else -move_pct
            if directional_move > threshold:
                outcome_status = "FAVORABLE"
                reason = self._directional_reason(hypothesis.direction_bias, move_pct, threshold, favorable=True)
            elif directional_move < -threshold:
                outcome_status = "UNFAVORABLE"
                reason = self._directional_reason(hypothesis.direction_bias, move_pct, threshold, favorable=False)
            else:
                outcome_status = "NEUTRAL"
                reason = (
                    f"{hypothesis.asset} moved {move_pct:+.2f}% by {horizon_hours}h, which stayed inside the "
                    f"neutral threshold of {threshold:.2f}%."
                )

        max_favorable_move_pct, max_adverse_move_pct = self._compute_path_stats(
            connection=connection,
            asset=hypothesis.asset,
            entry_point=entry_point,
            followup_point=followup_point,
            direction_bias=hypothesis.direction_bias,
        )

        return self._build_outcome(
            hypothesis=hypothesis,
            horizon_hours=horizon_hours,
            evaluated_at=evaluation_time,
            entry_point=entry_point,
            followup_point=followup_point,
            outcome_status=outcome_status,
            reason=reason,
            warnings=warnings,
            move_pct=move_pct,
            max_favorable_move_pct=max_favorable_move_pct,
            max_adverse_move_pct=max_adverse_move_pct,
        )

    def _fetch_hypotheses(
        self,
        connection: sqlite3.Connection,
        cutoff: datetime,
    ) -> list[_StoredHypothesis]:
        rows = connection.execute(
            """
            SELECT id, workflow_run_id, asset, hypothesis_name, direction_bias, hypothesis_status,
                   suggested_strategy_family, created_at
            FROM strategy_hypotheses
            WHERE created_at >= ?
            ORDER BY id ASC
            """,
            (cutoff.isoformat(),),
        ).fetchall()
        return [
            _StoredHypothesis(
                hypothesis_id=int(row["id"]),
                workflow_run_id=int(row["workflow_run_id"]),
                asset=str(row["asset"]),
                hypothesis_name=str(row["hypothesis_name"]),
                direction_bias=str(row["direction_bias"]),
                hypothesis_status=str(row["hypothesis_status"]),
                strategy_family=str(row["suggested_strategy_family"]),
                created_at=_parse_datetime(row["created_at"]),
            )
            for row in rows
        ]

    def _fetch_existing_outcome_statuses(
        self,
        connection: sqlite3.Connection,
    ) -> dict[tuple[int, int], str]:
        if not self._table_exists(connection, "strategy_hypothesis_outcomes"):
            return {}
        rows = connection.execute(
            "SELECT hypothesis_id, horizon_hours, outcome_status FROM strategy_hypothesis_outcomes"
        ).fetchall()
        return {
            (int(row["hypothesis_id"]), int(row["horizon_hours"])): str(row["outcome_status"])
            for row in rows
        }

    def _fetch_entry_reference_price(
        self,
        connection: sqlite3.Connection,
        asset: str,
        created_at: datetime,
        warnings: list[str],
    ) -> _SnapshotPricePoint | None:
        asset_name, data_type = self._price_source(asset)
        row = connection.execute(
            """
            SELECT timestamp, value_json
            FROM market_snapshots
            WHERE asset = ? AND data_type = ? AND status = 'OK' AND timestamp <= ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (asset_name, data_type, created_at.isoformat()),
        ).fetchone()
        if row:
            point = self._row_to_price_point(row)
            if point:
                return point

        fallback_row = connection.execute(
            """
            SELECT timestamp, value_json
            FROM market_snapshots
            WHERE asset = ? AND data_type = ? AND status = 'OK' AND timestamp >= ?
            ORDER BY timestamp ASC, id ASC
            LIMIT 1
            """,
            (asset_name, data_type, created_at.isoformat()),
        ).fetchone()
        point = self._row_to_price_point(fallback_row) if fallback_row else None
        if point:
            warnings.append(
                f"Entry reference for {asset} used the first persisted price after hypothesis creation because no earlier snapshot was available."
            )
        return point

    def _fetch_followup_price(
        self,
        connection: sqlite3.Connection,
        asset: str,
        target_time: datetime,
    ) -> _SnapshotPricePoint | None:
        asset_name, data_type = self._price_source(asset)
        row = connection.execute(
            """
            SELECT timestamp, value_json
            FROM market_snapshots
            WHERE asset = ? AND data_type = ? AND status = 'OK' AND timestamp >= ?
            ORDER BY timestamp ASC, id ASC
            LIMIT 1
            """,
            (asset_name, data_type, target_time.isoformat()),
        ).fetchone()
        return self._row_to_price_point(row) if row else None

    def _compute_path_stats(
        self,
        *,
        connection: sqlite3.Connection,
        asset: str,
        entry_point: _SnapshotPricePoint,
        followup_point: _SnapshotPricePoint,
        direction_bias: str,
    ) -> tuple[float | None, float | None]:
        if direction_bias not in {"LONG", "SHORT"}:
            return None, None

        asset_name, data_type = self._price_source(asset)
        rows = connection.execute(
            """
            SELECT timestamp, value_json
            FROM market_snapshots
            WHERE asset = ? AND data_type = ? AND status = 'OK' AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC, id ASC
            """,
            (asset_name, data_type, entry_point.timestamp.isoformat(), followup_point.timestamp.isoformat()),
        ).fetchall()

        directional_moves: list[float] = []
        for row in rows:
            point = self._row_to_price_point(row)
            if point is None:
                continue
            raw_move_pct = ((point.price - entry_point.price) / entry_point.price) * 100.0
            directional_moves.append(raw_move_pct if direction_bias == "LONG" else -raw_move_pct)

        if not directional_moves:
            return None, None

        max_favorable = max(0.0, max(directional_moves))
        max_adverse = max(0.0, max(-move for move in directional_moves))
        return round(max_favorable, 6), round(max_adverse, 6)

    def _build_outcome(
        self,
        *,
        hypothesis: _StoredHypothesis,
        horizon_hours: int,
        evaluated_at: datetime,
        entry_point: _SnapshotPricePoint | None,
        followup_point: _SnapshotPricePoint | None,
        outcome_status: str,
        reason: str,
        warnings: list[str],
        move_pct: float | None = None,
        max_favorable_move_pct: float | None = None,
        max_adverse_move_pct: float | None = None,
    ) -> HypothesisOutcome:
        return HypothesisOutcome(
            hypothesis_id=hypothesis.hypothesis_id,
            workflow_run_id=hypothesis.workflow_run_id,
            asset=hypothesis.asset,
            hypothesis_name=hypothesis.hypothesis_name,
            direction_bias=hypothesis.direction_bias,
            strategy_family=hypothesis.strategy_family,
            horizon_hours=horizon_hours,
            created_at=hypothesis.created_at,
            evaluated_at=evaluated_at,
            entry_reference_price=entry_point.price if entry_point else None,
            followup_price=followup_point.price if followup_point else None,
            move_pct=round(move_pct, 6) if move_pct is not None else None,
            max_favorable_move_pct=max_favorable_move_pct,
            max_adverse_move_pct=max_adverse_move_pct,
            outcome_status=outcome_status,
            reason=reason,
            warnings=_unique_items(warnings),
        )

    @staticmethod
    def _directional_reason(direction_bias: str, move_pct: float, threshold: float, favorable: bool) -> str:
        qualifier = "favorable" if favorable else "unfavorable"
        if direction_bias == "LONG":
            return (
                f"LONG hypothesis saw a {move_pct:+.2f}% move by the evaluation horizon, which was "
                f"{qualifier} versus the neutral threshold of {threshold:.2f}%."
            )
        return (
            f"SHORT hypothesis saw a {move_pct:+.2f}% underlying move by the evaluation horizon, which was "
            f"{qualifier} versus the neutral threshold of {threshold:.2f}%."
        )

    @staticmethod
    def _price_source(asset: str) -> tuple[str, str]:
        if asset == "BTC":
            return "BTC", "price"
        return "Gold", "spot_price"

    @staticmethod
    def _row_to_price_point(row: sqlite3.Row | dict[str, Any] | None) -> _SnapshotPricePoint | None:
        if row is None:
            return None
        raw_payload = row["value_json"] if isinstance(row, sqlite3.Row) else row.get("value_json")
        payload = _json_object(raw_payload)
        price = None
        if "price" in payload:
            price = _coerce_float(payload.get("price"))
        elif "latest_value" in payload:
            price = _coerce_float(payload.get("latest_value"))
        if price is None:
            return None
        raw_timestamp = row["timestamp"] if isinstance(row, sqlite3.Row) else row.get("timestamp")
        return _SnapshotPricePoint(timestamp=_parse_datetime(raw_timestamp), price=price)

    def _connect_read_only(self) -> sqlite3.Connection:
        assert self.database_path is not None
        uri = f"{self.database_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _row_to_outcome(row: dict[str, Any]) -> HypothesisOutcome:
        return HypothesisOutcome(
            hypothesis_id=int(row.get("hypothesis_id") or 0),
            workflow_run_id=int(row.get("workflow_run_id") or 0),
            asset=str(row.get("asset") or "UNKNOWN"),
            hypothesis_name=str(row.get("hypothesis_name") or ""),
            direction_bias=str(row.get("direction_bias") or "NO_TRADE"),
            strategy_family=str(row.get("strategy_family") or ""),
            horizon_hours=int(row.get("horizon_hours") or 0),
            created_at=_parse_datetime(row.get("created_at")),
            evaluated_at=_parse_datetime(row.get("evaluated_at")),
            entry_reference_price=_coerce_float(row.get("entry_reference_price")),
            followup_price=_coerce_float(row.get("followup_price")),
            move_pct=_coerce_float(row.get("move_pct")),
            max_favorable_move_pct=_coerce_float(row.get("max_favorable_move_pct")),
            max_adverse_move_pct=_coerce_float(row.get("max_adverse_move_pct")),
            outcome_status=str(row.get("outcome_status") or "INSUFFICIENT_FOLLOWUP_DATA"),
            reason=str(row.get("reason") or ""),
            warnings=_json_list(row.get("warnings_json")),
        )


def _parse_datetime(raw_value: Any) -> datetime:
    if raw_value in {None, ""}:
        return datetime.now(UTC)
    text = str(raw_value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _json_object(raw_value: Any) -> dict[str, Any]:
    if raw_value in {None, ""}:
        return {}
    try:
        parsed = json.loads(str(raw_value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(raw_value: Any) -> list[str]:
    if raw_value in {None, ""}:
        return []
    try:
        parsed = json.loads(str(raw_value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique_items(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in unique:
            continue
        unique.append(normalized)
    return unique
