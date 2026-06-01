from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.models import MultiPointTrendResult, TrendResult


@dataclass(frozen=True)
class TrendSpec:
    key: str
    asset: str
    data_type: str
    value_field: str
    label: str


class TrendAnalyzer:
    """Computes simple read-only trends from persisted market_snapshots."""

    DEFAULT_SPECS = [
        TrendSpec("btc_price", "BTC", "price", "price", "BTC price"),
        TrendSpec("btc_fear_greed", "BTC", "fear_and_greed_index", "value", "BTC Fear & Greed"),
        TrendSpec("btc_funding_rate", "BTC", "funding_rate", "funding_rate", "BTC funding rate"),
        TrendSpec("btc_open_interest", "BTC", "open_interest", "open_interest", "BTC open interest"),
        TrendSpec("gold_us10y", "Gold", "us10y", "latest_value", "US10Y"),
        TrendSpec("gold_real_yield", "Gold", "real_yield", "latest_value", "Real yield"),
        TrendSpec("gold_fed_funds", "Gold", "fed_funds", "latest_value", "Fed Funds"),
        TrendSpec("gold_cpi", "Gold", "cpi", "latest_value", "CPI"),
    ]

    def __init__(self, database_path: Path, lookback_points: int = 5) -> None:
        self.database_path = database_path
        self.lookback_points = max(2, lookback_points)

    def analyze_all(self) -> dict[str, TrendResult]:
        if not self.database_path.exists():
            return {
                spec.key: self._not_available(spec, f"Database not found at {self.database_path}.")
                for spec in self.DEFAULT_SPECS
            }

        try:
            with self._connect_read_only() as connection:
                connection.row_factory = sqlite3.Row
                if not self._table_exists(connection):
                    return {
                        spec.key: self._not_available(spec, "market_snapshots table is not available.")
                        for spec in self.DEFAULT_SPECS
                    }

                results: dict[str, TrendResult] = {}
                for spec in self.DEFAULT_SPECS:
                    price_trend = results.get("btc_price") if spec.key == "btc_open_interest" else None
                    results[spec.key] = self._analyze_spec(connection, spec, price_trend)
                return results
        except sqlite3.Error as exc:
            return {
                spec.key: self._failure(spec, f"Trend analysis failed while reading SQLite: {exc}")
                for spec in self.DEFAULT_SPECS
            }

    def analyze_all_multipoint(self, lookback_points: int | None = None) -> dict[str, MultiPointTrendResult]:
        effective_lookback = max(3, lookback_points or self.lookback_points)
        if not self.database_path.exists():
            return {
                spec.key: self._multipoint_not_available(spec, f"Database not found at {self.database_path}.")
                for spec in self.DEFAULT_SPECS
            }

        try:
            with self._connect_read_only() as connection:
                connection.row_factory = sqlite3.Row
                if not self._table_exists(connection):
                    return {
                        spec.key: self._multipoint_not_available(spec, "market_snapshots table is not available.")
                        for spec in self.DEFAULT_SPECS
                    }

                results: dict[str, MultiPointTrendResult] = {}
                for spec in self.DEFAULT_SPECS:
                    price_trend = results.get("btc_price") if spec.key == "btc_open_interest" else None
                    results[spec.key] = self._analyze_spec_multipoint(
                        connection,
                        spec,
                        effective_lookback,
                        price_trend,
                    )
                return results
        except sqlite3.Error as exc:
            return {
                spec.key: self._multipoint_failure(spec, f"Multi-point trend analysis failed while reading SQLite: {exc}")
                for spec in self.DEFAULT_SPECS
            }

    def _analyze_spec(
        self,
        connection: sqlite3.Connection,
        spec: TrendSpec,
        price_trend: TrendResult | None = None,
    ) -> TrendResult:
        values = self._fetch_numeric_values(connection, spec, self.lookback_points)

        if len(values) < 2:
            latest_value = values[0] if values else None
            return TrendResult(
                asset=spec.asset,
                data_type=spec.data_type,
                status="INSUFFICIENT_HISTORY",
                latest_value=latest_value,
                previous_value=None,
                change_abs=None,
                change_pct=None,
                direction="unknown",
                lookback_points=len(values),
                reason=f"{spec.label} needs at least two persisted OK snapshots for trend analysis.",
            )

        latest_value = values[0]
        previous_value = values[1]
        change_abs = latest_value - previous_value
        change_pct = (change_abs / abs(previous_value)) * 100 if previous_value != 0 else None
        direction = self._direction(change_abs)

        return TrendResult(
            asset=spec.asset,
            data_type=spec.data_type,
            status="OK",
            latest_value=latest_value,
            previous_value=previous_value,
            change_abs=change_abs,
            change_pct=change_pct,
            direction=direction,
            lookback_points=len(values),
            reason=self._build_reason(spec, direction, price_trend),
        )

    def _analyze_spec_multipoint(
        self,
        connection: sqlite3.Connection,
        spec: TrendSpec,
        lookback_points: int,
        price_trend: MultiPointTrendResult | None = None,
    ) -> MultiPointTrendResult:
        values_latest_first = self._fetch_numeric_values(connection, spec, lookback_points)
        if len(values_latest_first) < 3:
            return self._multipoint_insufficient(spec, values_latest_first)

        chronological_values = list(reversed(values_latest_first))
        first_value = chronological_values[0]
        latest_value = chronological_values[-1]
        change_abs = latest_value - first_value
        change_pct = (change_abs / abs(first_value)) * 100 if first_value != 0 else None
        direction = self._multipoint_direction(chronological_values)
        trend_strength = self._trend_strength(direction, change_abs, change_pct)

        return MultiPointTrendResult(
            asset=spec.asset,
            data_type=spec.data_type,
            status="OK",
            latest_value=latest_value,
            first_value=first_value,
            average_value=sum(chronological_values) / len(chronological_values),
            min_value=min(chronological_values),
            max_value=max(chronological_values),
            change_abs=change_abs,
            change_pct=change_pct,
            direction=direction,
            trend_strength=trend_strength,
            lookback_points=len(chronological_values),
            reason=self._build_multipoint_reason(spec, direction, trend_strength, len(chronological_values), price_trend),
        )

    def _fetch_numeric_values(self, connection: sqlite3.Connection, spec: TrendSpec, limit: int) -> list[float]:
        rows = connection.execute(
            """
            SELECT id, timestamp, value_json
            FROM market_snapshots
            WHERE asset = ?
              AND data_type = ?
              AND status = 'OK'
              AND value_json IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (spec.asset, spec.data_type, limit),
        ).fetchall()

        values: list[float] = []
        for row in rows:
            value = self._extract_numeric_value(row["value_json"], spec.value_field)
            if value is not None:
                values.append(value)
        return values

    @staticmethod
    def _extract_numeric_value(value_json: str, value_field: str) -> float | None:
        try:
            payload = json.loads(value_json)
        except json.JSONDecodeError:
            return None

        if not isinstance(payload, dict) or value_field not in payload:
            return None

        try:
            return float(payload[value_field])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _direction(change_abs: float) -> str:
        if change_abs > 0:
            return "rising"
        if change_abs < 0:
            return "falling"
        return "flat"

    @staticmethod
    def _multipoint_direction(values: list[float]) -> str:
        if len(values) < 2:
            return "unknown"

        positive_steps = 0
        negative_steps = 0
        for previous, current in zip(values, values[1:]):
            change = current - previous
            if change > 0:
                positive_steps += 1
            elif change < 0:
                negative_steps += 1

        if positive_steps and negative_steps:
            return "mixed"
        if positive_steps:
            return "rising"
        if negative_steps:
            return "falling"
        return "flat"

    @staticmethod
    def _trend_strength(direction: str, change_abs: float, change_pct: float | None) -> str:
        if direction == "unknown":
            return "unknown"
        if direction == "flat":
            return "weak"
        if change_pct is None:
            return "unknown" if change_abs else "weak"

        magnitude = abs(change_pct)
        if direction == "mixed":
            return "moderate" if magnitude >= 5 else "weak"
        if magnitude >= 5:
            return "strong"
        if magnitude >= 1:
            return "moderate"
        return "weak"

    @staticmethod
    def _build_reason(spec: TrendSpec, direction: str, price_trend: TrendResult | None) -> str:
        if spec.key == "btc_open_interest":
            if direction == "rising" and price_trend and price_trend.direction == "rising":
                return "BTC open interest is rising while price is rising, suggesting trend participation and leverage build-up."
            if direction == "rising" and price_trend and price_trend.direction == "falling":
                return "BTC open interest is rising while price is falling, suggesting possible bearish pressure."
            if direction == "falling":
                return "BTC open interest is falling, suggesting deleveraging or lower participation."
            return "BTC open interest trend is flat or lacks price confirmation."

        if spec.key == "gold_us10y":
            if direction == "falling":
                return "US10Y is falling versus the previous persisted snapshot, which is generally supportive for gold."
            if direction == "rising":
                return "US10Y is rising versus the previous persisted snapshot, which generally pressures gold."

        if spec.key == "gold_real_yield":
            if direction == "falling":
                return "Real yield is falling versus the previous persisted snapshot, which is generally supportive for gold."
            if direction == "rising":
                return "Real yield is rising versus the previous persisted snapshot, which generally pressures gold."

        if spec.key in {"gold_fed_funds", "gold_cpi"}:
            return f"{spec.label} trend is {direction}; it is tracked as macro context for now."

        return f"{spec.label} is {direction} versus the previous persisted snapshot."

    @staticmethod
    def _build_multipoint_reason(
        spec: TrendSpec,
        direction: str,
        strength: str,
        lookback_points: int,
        price_trend: MultiPointTrendResult | None,
    ) -> str:
        if spec.key == "btc_open_interest":
            if direction == "rising" and price_trend and price_trend.direction == "rising":
                return (
                    "BTC open interest and price are rising across the multi-point lookback, "
                    "suggesting trend participation and leverage build-up."
                )
            if direction == "rising" and price_trend and price_trend.direction == "falling":
                return (
                    "BTC open interest is rising while price is falling across the multi-point lookback, "
                    "suggesting possible bearish pressure."
                )
            if direction == "falling":
                return "BTC open interest is falling across the multi-point lookback, suggesting deleveraging."
            if direction == "mixed":
                return "BTC open interest is mixed across the multi-point lookback; participation is not directional yet."
            return "BTC open interest is flat or lacks price confirmation across the multi-point lookback."

        if spec.key == "gold_us10y":
            if direction == "falling":
                return "US10Y is falling across the multi-point lookback, which is generally supportive for gold."
            if direction == "rising":
                return "US10Y is rising across the multi-point lookback, which generally pressures gold."

        if spec.key == "gold_real_yield":
            if direction == "falling":
                return "Real yield is falling across the multi-point lookback, which is generally supportive for gold."
            if direction == "rising":
                return "Real yield is rising across the multi-point lookback, which generally pressures gold."

        if spec.key in {"gold_fed_funds", "gold_cpi"}:
            return (
                f"{spec.label} multi-point trend is {direction} with {strength} strength across "
                f"{lookback_points} persisted OK snapshots; it is tracked as macro context for now."
            )

        return (
            f"{spec.label} multi-point trend is {direction} with {strength} strength across "
            f"{lookback_points} persisted OK snapshots."
        )

    @staticmethod
    def _table_exists(connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'market_snapshots'"
        ).fetchone()
        return row is not None

    def _connect_read_only(self) -> sqlite3.Connection:
        uri = f"{self.database_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _not_available(spec: TrendSpec, reason: str) -> TrendResult:
        return TrendResult(
            asset=spec.asset,
            data_type=spec.data_type,
            status="NOT_AVAILABLE",
            latest_value=None,
            previous_value=None,
            change_abs=None,
            change_pct=None,
            direction="unknown",
            lookback_points=0,
            reason=reason,
        )

    @staticmethod
    def _failure(spec: TrendSpec, reason: str) -> TrendResult:
        return TrendResult(
            asset=spec.asset,
            data_type=spec.data_type,
            status="FAIL",
            latest_value=None,
            previous_value=None,
            change_abs=None,
            change_pct=None,
            direction="unknown",
            lookback_points=0,
            reason=reason,
        )

    @staticmethod
    def _multipoint_insufficient(spec: TrendSpec, values_latest_first: list[float]) -> MultiPointTrendResult:
        chronological_values = list(reversed(values_latest_first))
        latest_value = chronological_values[-1] if chronological_values else None
        first_value = chronological_values[0] if chronological_values else None
        average_value = sum(chronological_values) / len(chronological_values) if chronological_values else None
        return MultiPointTrendResult(
            asset=spec.asset,
            data_type=spec.data_type,
            status="INSUFFICIENT_HISTORY",
            latest_value=latest_value,
            first_value=first_value,
            average_value=average_value,
            min_value=min(chronological_values) if chronological_values else None,
            max_value=max(chronological_values) if chronological_values else None,
            change_abs=None,
            change_pct=None,
            direction="unknown",
            trend_strength="unknown",
            lookback_points=len(chronological_values),
            reason=f"{spec.label} needs at least three persisted OK snapshots for multi-point trend analysis.",
        )

    @staticmethod
    def _multipoint_not_available(spec: TrendSpec, reason: str) -> MultiPointTrendResult:
        return MultiPointTrendResult(
            asset=spec.asset,
            data_type=spec.data_type,
            status="NOT_AVAILABLE",
            latest_value=None,
            first_value=None,
            average_value=None,
            min_value=None,
            max_value=None,
            change_abs=None,
            change_pct=None,
            direction="unknown",
            trend_strength="unknown",
            lookback_points=0,
            reason=reason,
        )

    @staticmethod
    def _multipoint_failure(spec: TrendSpec, reason: str) -> MultiPointTrendResult:
        return MultiPointTrendResult(
            asset=spec.asset,
            data_type=spec.data_type,
            status="FAIL",
            latest_value=None,
            first_value=None,
            average_value=None,
            min_value=None,
            max_value=None,
            change_abs=None,
            change_pct=None,
            direction="unknown",
            trend_strength="unknown",
            lookback_points=0,
            reason=reason,
        )
