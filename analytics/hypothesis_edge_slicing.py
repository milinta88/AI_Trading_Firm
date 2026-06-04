from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.config import HypothesisEdgeSlicingConfig, HypothesisReviewBucketsConfig
from core.models import HypothesisEdgeSliceRow, HypothesisEdgeSliceSummary


_EVALUATED_STATUSES = {"FAVORABLE", "UNFAVORABLE", "NEUTRAL"}
_POSITIVE_STATUSES = {"STRONG_POSITIVE", "WEAK_POSITIVE"}
_NEGATIVE_STATUSES = {"NEGATIVE", "HIGH_ADVERSE_MOVE"}
_UNSTABLE_STATUSES = {"MIXED_OR_UNSTABLE", "NEUTRAL", "INSUFFICIENT_SAMPLE"}
_STABILITY_ORDER = {
    "STRONG_POSITIVE": 0,
    "WEAK_POSITIVE": 1,
    "NEUTRAL": 2,
    "MIXED_OR_UNSTABLE": 3,
    "INSUFFICIENT_SAMPLE": 4,
    "NEGATIVE": 5,
    "HIGH_ADVERSE_MOVE": 6,
}


class HypothesisEdgeSlicingAnalyzer:
    """Builds read-only slice analytics over persisted hypothesis outcomes."""

    def __init__(
        self,
        *,
        database_path: Path | None,
        config: HypothesisEdgeSlicingConfig,
        readiness_buckets: HypothesisReviewBucketsConfig,
    ) -> None:
        self.database_path = database_path
        self.config = config
        self.readiness_buckets = readiness_buckets

    def build_summary(self, now: datetime | None = None) -> HypothesisEdgeSliceSummary:
        generated_at = now.astimezone(UTC) if now else datetime.now(UTC)
        empty = self._empty_summary(generated_at=generated_at)

        if not self.config.enabled:
            return self._with_warning(empty, "Hypothesis edge slicing is disabled in config.")
        if not self.database_path or not self.database_path.exists():
            return self._with_warning(empty, "SQLite database is not available for hypothesis edge slicing.")

        try:
            with self._connect_read_only() as connection:
                rows = self._fetch_joined_outcome_rows(connection, reference_time=generated_at)
        except sqlite3.Error:
            return self._with_warning(empty, "Unable to read hypothesis edge slicing data from SQLite.")

        if not rows:
            return self._with_warning(empty, "No persisted strategy hypothesis outcomes are available yet.")

        normalized_rows = [self._normalize_row(row) for row in rows]
        evaluated_rows = [row for row in normalized_rows if row["outcome_status"] in _EVALUATED_STATUSES]

        warnings: list[str] = []
        ignored_count = len(normalized_rows) - len(evaluated_rows)
        if ignored_count:
            warnings.append(
                f"{ignored_count} persisted outcome rows were excluded because they were blocked or missing follow-up data."
            )
        if not evaluated_rows:
            return self._with_warning(
                empty,
                "No evaluated hypothesis outcomes are available yet for edge slicing.",
            )

        slice_rows = self._build_slice_rows(evaluated_rows)
        insufficient_count = sum(1 for row in slice_rows if row.stability_status == "INSUFFICIENT_SAMPLE")
        if insufficient_count:
            warnings.append(
                f"{insufficient_count} slices remain below the minimum sample size of {self.config.min_samples_per_slice}."
            )

        strongest_slices = self._select_strongest_slices(slice_rows)
        weakest_slices = self._select_weakest_slices(slice_rows)
        unstable_slices = self._select_unstable_slices(slice_rows)

        return HypothesisEdgeSliceSummary(
            total_slices=len(slice_rows),
            generated_at=generated_at,
            lookback_days=self.config.lookback_days,
            slice_rows=slice_rows,
            warnings=_unique_strings(warnings),
            strongest_slices=strongest_slices,
            weakest_slices=weakest_slices,
            unstable_slices=unstable_slices,
        )

    def load_latest_summary(self) -> HypothesisEdgeSliceSummary | None:
        if not self.database_path or not self.database_path.exists():
            return None

        try:
            with self._connect_read_only() as connection:
                if not self._table_exists(connection, "hypothesis_edge_slice_summaries"):
                    return None
                row = connection.execute(
                    "SELECT * FROM hypothesis_edge_slice_summaries ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if row is None:
                    return None
                slice_rows = self._load_slice_rows(connection, int(row["id"]))
        except sqlite3.Error:
            return None

        return self._row_to_summary(dict(row), slice_rows=slice_rows)

    def load_recent_summaries(self, limit: int = 10) -> list[HypothesisEdgeSliceSummary]:
        if not self.database_path or not self.database_path.exists():
            return []

        try:
            with self._connect_read_only() as connection:
                if not self._table_exists(connection, "hypothesis_edge_slice_summaries"):
                    return []
                rows = connection.execute(
                    "SELECT * FROM hypothesis_edge_slice_summaries ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        except sqlite3.Error:
            return []

        return [self._row_to_summary(dict(row), slice_rows=[]) for row in rows]

    def _fetch_joined_outcome_rows(
        self,
        connection: sqlite3.Connection,
        *,
        reference_time: datetime,
    ) -> list[dict[str, Any]]:
        if not self._table_exists(connection, "strategy_hypothesis_outcomes"):
            return []
        if not self._table_exists(connection, "strategy_hypotheses"):
            return []

        cutoff = (reference_time - timedelta(days=self.config.lookback_days)).isoformat()
        rows = connection.execute(
            """
            SELECT
                o.*,
                COALESCE(h.regime, 'UNKNOWN') AS regime,
                COALESCE(h.readiness_score, 0) AS readiness_score,
                COALESCE(h.confidence, 'UNKNOWN') AS confidence,
                COALESCE(h.hypothesis_status, 'UNKNOWN') AS hypothesis_status
            FROM strategy_hypothesis_outcomes o
            LEFT JOIN strategy_hypotheses h ON h.id = o.hypothesis_id
            WHERE o.created_at >= ?
            ORDER BY o.id DESC
            """,
            (cutoff,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _build_slice_rows(self, rows: list[dict[str, Any]]) -> list[HypothesisEdgeSliceRow]:
        grouped: dict[tuple[str, str, str, int, str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            key = (
                str(row.get("asset") or "UNKNOWN"),
                str(row.get("strategy_family") or "UNKNOWN"),
                str(row.get("regime") or "UNKNOWN"),
                int(row.get("horizon_hours") or 0),
                str(row.get("readiness_bucket") or "UNKNOWN"),
                str(row.get("confidence_bucket") or "UNKNOWN"),
                str(row.get("weekday") or "UNKNOWN"),
            )
            grouped.setdefault(key, []).append(row)

        slice_rows: list[HypothesisEdgeSliceRow] = []
        for key in sorted(grouped):
            group_rows = grouped[key]
            slice_rows.append(self._summarize_slice_group(key, group_rows))
        return slice_rows

    def _summarize_slice_group(
        self,
        key: tuple[str, str, str, int, str, str, str],
        group_rows: list[dict[str, Any]],
    ) -> HypothesisEdgeSliceRow:
        asset, strategy_family, regime, horizon_hours, readiness_bucket, confidence_bucket, weekday = key
        favorable_count = sum(1 for row in group_rows if row["outcome_status"] == "FAVORABLE")
        unfavorable_count = sum(1 for row in group_rows if row["outcome_status"] == "UNFAVORABLE")
        neutral_count = sum(1 for row in group_rows if row["outcome_status"] == "NEUTRAL")
        sample_size = len(group_rows)
        favorable_rate = _safe_rate(favorable_count, sample_size)
        unfavorable_rate = _safe_rate(unfavorable_count, sample_size)
        neutral_rate = _safe_rate(neutral_count, sample_size)
        avg_move_pct = _average(group_rows, "move_pct")
        avg_mfe = _average(group_rows, "max_favorable_move_pct")
        avg_mae = _average(group_rows, "max_adverse_move_pct")

        stability_status, row_warnings = self._classify_stability(
            asset=asset,
            strategy_family=strategy_family,
            sample_size=sample_size,
            favorable_rate=favorable_rate,
            unfavorable_rate=unfavorable_rate,
            neutral_rate=neutral_rate,
            avg_max_adverse_move_pct=avg_mae,
        )
        candidate_status = self._candidate_status(strategy_family, stability_status)
        warnings = _unique_strings(
            [*row_warnings, *_flatten_warning_lists(group_rows)]
        )
        slice_key = "|".join(
            [
                asset,
                strategy_family,
                regime,
                str(horizon_hours),
                readiness_bucket,
                confidence_bucket,
                weekday,
            ]
        )

        return HypothesisEdgeSliceRow(
            slice_key=slice_key,
            asset=asset,
            strategy_family=strategy_family,
            regime=regime,
            horizon_hours=horizon_hours,
            readiness_bucket=readiness_bucket,
            confidence_bucket=confidence_bucket,
            weekday=weekday,
            sample_size=sample_size,
            favorable_count=favorable_count,
            unfavorable_count=unfavorable_count,
            neutral_count=neutral_count,
            favorable_rate=favorable_rate,
            unfavorable_rate=unfavorable_rate,
            neutral_rate=neutral_rate,
            avg_move_pct=avg_move_pct,
            avg_max_favorable_move_pct=avg_mfe,
            avg_max_adverse_move_pct=avg_mae,
            stability_status=stability_status,
            candidate_status=candidate_status,
            warnings=warnings,
        )

    def _classify_stability(
        self,
        *,
        asset: str,
        strategy_family: str,
        sample_size: int,
        favorable_rate: float,
        unfavorable_rate: float,
        neutral_rate: float,
        avg_max_adverse_move_pct: float | None,
    ) -> tuple[str, list[str]]:
        warnings: list[str] = []
        adverse_limit = float(self.config.max_avg_adverse_move_pct.get(asset, float("inf")))

        if strategy_family.endswith("_NO_TRADE"):
            warnings.append("No-trade strategy families remain blocked in edge slicing review.")
            return "MIXED_OR_UNSTABLE", warnings
        if sample_size < self.config.min_samples_per_slice:
            warnings.append(
                f"Sample size {sample_size} is below the minimum {self.config.min_samples_per_slice}."
            )
            return "INSUFFICIENT_SAMPLE", warnings
        if avg_max_adverse_move_pct is not None and avg_max_adverse_move_pct > adverse_limit:
            warnings.append(
                f"Average adverse move {avg_max_adverse_move_pct:.2f}% is above the {asset} limit of {adverse_limit:.2f}%."
            )
            return "HIGH_ADVERSE_MOVE", warnings
        if unfavorable_rate > self.config.max_unfavorable_rate:
            warnings.append(
                f"Unfavorable rate {unfavorable_rate:.0%} is above the allowed {self.config.max_unfavorable_rate:.0%}."
            )
            return "NEGATIVE", warnings
        if favorable_rate >= self.config.strong_favorable_rate and unfavorable_rate <= self.config.max_unfavorable_rate:
            return "STRONG_POSITIVE", warnings
        if favorable_rate >= self.config.weak_favorable_rate and unfavorable_rate <= self.config.max_unfavorable_rate:
            return "WEAK_POSITIVE", warnings
        if neutral_rate >= max(favorable_rate, unfavorable_rate):
            return "NEUTRAL", warnings
        return "MIXED_OR_UNSTABLE", warnings

    @staticmethod
    def _candidate_status(strategy_family: str, stability_status: str) -> str:
        if strategy_family.endswith("_NO_TRADE"):
            return "BLOCKED"
        if stability_status == "INSUFFICIENT_SAMPLE":
            return "NEED_MORE_SAMPLES"
        if stability_status in _POSITIVE_STATUSES:
            return "REVIEW_CANDIDATE"
        if stability_status in {"NEUTRAL", "MIXED_OR_UNSTABLE"}:
            return "WATCH"
        return "BLOCKED"

    def _select_strongest_slices(self, slice_rows: list[HypothesisEdgeSliceRow]) -> list[HypothesisEdgeSliceRow]:
        candidates = [row for row in slice_rows if row.stability_status in _POSITIVE_STATUSES]
        return sorted(
            candidates,
            key=lambda row: (
                _STABILITY_ORDER.get(row.stability_status, 99),
                -row.favorable_rate,
                -row.sample_size,
                row.avg_max_adverse_move_pct if row.avg_max_adverse_move_pct is not None else float("inf"),
                row.slice_key,
            ),
        )[:5]

    def _select_weakest_slices(self, slice_rows: list[HypothesisEdgeSliceRow]) -> list[HypothesisEdgeSliceRow]:
        candidates = [row for row in slice_rows if row.stability_status in _NEGATIVE_STATUSES]
        return sorted(
            candidates,
            key=lambda row: (
                _STABILITY_ORDER.get(row.stability_status, 99),
                -(row.avg_max_adverse_move_pct or 0.0),
                -row.unfavorable_rate,
                -row.sample_size,
                row.slice_key,
            ),
        )[:5]

    def _select_unstable_slices(self, slice_rows: list[HypothesisEdgeSliceRow]) -> list[HypothesisEdgeSliceRow]:
        candidates = [row for row in slice_rows if row.stability_status in _UNSTABLE_STATUSES]
        return sorted(
            candidates,
            key=lambda row: (
                _STABILITY_ORDER.get(row.stability_status, 99),
                row.sample_size,
                -row.unfavorable_rate,
                row.slice_key,
            ),
        )[:5]

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        normalized["asset"] = str(normalized.get("asset") or "UNKNOWN")
        normalized["strategy_family"] = str(normalized.get("strategy_family") or "UNKNOWN")
        normalized["regime"] = str(normalized.get("regime") or "UNKNOWN")
        normalized["horizon_hours"] = int(normalized.get("horizon_hours") or 0)
        normalized["outcome_status"] = str(normalized.get("outcome_status") or "UNKNOWN")
        normalized["readiness_score"] = int(normalized.get("readiness_score") or 0)
        normalized["readiness_bucket"] = _readiness_bucket(
            normalized["readiness_score"],
            self.readiness_buckets,
        )
        normalized["confidence_bucket"] = _confidence_bucket(normalized.get("confidence"))
        normalized["weekday"] = _weekday_label(normalized.get("created_at"))
        normalized["warnings"] = _json_list(normalized.get("warnings_json"))
        return normalized

    def _empty_summary(self, *, generated_at: datetime) -> HypothesisEdgeSliceSummary:
        return HypothesisEdgeSliceSummary(
            total_slices=0,
            generated_at=generated_at,
            lookback_days=self.config.lookback_days,
            slice_rows=[],
            warnings=[],
            strongest_slices=[],
            weakest_slices=[],
            unstable_slices=[],
        )

    @staticmethod
    def _with_warning(summary: HypothesisEdgeSliceSummary, warning: str) -> HypothesisEdgeSliceSummary:
        return HypothesisEdgeSliceSummary(
            total_slices=summary.total_slices,
            generated_at=summary.generated_at,
            lookback_days=summary.lookback_days,
            slice_rows=summary.slice_rows,
            warnings=_unique_strings([*summary.warnings, warning]),
            strongest_slices=summary.strongest_slices,
            weakest_slices=summary.weakest_slices,
            unstable_slices=summary.unstable_slices,
        )

    def _load_slice_rows(self, connection: sqlite3.Connection, summary_id: int) -> list[HypothesisEdgeSliceRow]:
        if not self._table_exists(connection, "hypothesis_edge_slice_rows"):
            return []
        rows = connection.execute(
            "SELECT * FROM hypothesis_edge_slice_rows WHERE summary_id = ? ORDER BY id ASC",
            (summary_id,),
        ).fetchall()
        return [self._row_to_slice_row(dict(row)) for row in rows]

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

    @classmethod
    def _row_to_summary(
        cls,
        row: dict[str, Any],
        *,
        slice_rows: list[HypothesisEdgeSliceRow],
    ) -> HypothesisEdgeSliceSummary:
        return HypothesisEdgeSliceSummary(
            total_slices=int(row.get("total_slices") or 0),
            generated_at=_parse_datetime(row.get("created_at")),
            lookback_days=int(row.get("lookback_days") or 0),
            slice_rows=slice_rows,
            warnings=_json_list(row.get("warnings_json")),
            strongest_slices=_json_slice_rows(row.get("strongest_slices_json")),
            weakest_slices=_json_slice_rows(row.get("weakest_slices_json")),
            unstable_slices=_json_slice_rows(row.get("unstable_slices_json")),
        )

    @staticmethod
    def _row_to_slice_row(row: dict[str, Any]) -> HypothesisEdgeSliceRow:
        return HypothesisEdgeSliceRow(
            slice_key=str(row.get("slice_key") or ""),
            asset=str(row.get("asset") or "UNKNOWN"),
            strategy_family=str(row.get("strategy_family") or "UNKNOWN"),
            regime=str(row.get("regime") or "UNKNOWN"),
            horizon_hours=int(row.get("horizon_hours") or 0),
            readiness_bucket=str(row.get("readiness_bucket") or "UNKNOWN"),
            confidence_bucket=str(row.get("confidence_bucket") or "UNKNOWN"),
            weekday=str(row.get("weekday") or "UNKNOWN"),
            sample_size=int(row.get("sample_size") or 0),
            favorable_count=int(row.get("favorable_count") or 0),
            unfavorable_count=int(row.get("unfavorable_count") or 0),
            neutral_count=int(row.get("neutral_count") or 0),
            favorable_rate=float(row.get("favorable_rate") or 0.0),
            unfavorable_rate=float(row.get("unfavorable_rate") or 0.0),
            neutral_rate=float(row.get("neutral_rate") or 0.0),
            avg_move_pct=_coerce_float(row.get("avg_move_pct")),
            avg_max_favorable_move_pct=_coerce_float(row.get("avg_max_favorable_move_pct")),
            avg_max_adverse_move_pct=_coerce_float(row.get("avg_max_adverse_move_pct")),
            stability_status=str(row.get("stability_status") or "INSUFFICIENT_SAMPLE"),
            candidate_status=str(row.get("candidate_status") or "BLOCKED"),
            warnings=_json_list(row.get("warnings_json")),
        )


def _readiness_bucket(score: int, buckets: HypothesisReviewBucketsConfig) -> str:
    if score < buckets.low_below:
        return "LOW"
    if score < buckets.medium_below:
        return "MEDIUM"
    return "HIGH"


def _confidence_bucket(confidence: Any) -> str:
    normalized = str(confidence or "").strip().upper()
    if normalized in {"LOW", "MEDIUM", "HIGH"}:
        return normalized
    return "UNKNOWN"


def _weekday_label(raw_value: Any) -> str:
    parsed = _parse_datetime(raw_value)
    return parsed.strftime("%A").upper()


def _parse_datetime(raw_value: Any) -> datetime:
    if raw_value in {None, ""}:
        return datetime.now(UTC)
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is None:
            return raw_value.replace(tzinfo=UTC)
        return raw_value.astimezone(UTC)
    text = str(raw_value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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


def _json_slice_rows(raw_value: Any) -> list[HypothesisEdgeSliceRow]:
    if raw_value in {None, ""}:
        return []
    try:
        parsed = json.loads(str(raw_value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    rows: list[HypothesisEdgeSliceRow] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        rows.append(
            HypothesisEdgeSliceRow(
                slice_key=str(item.get("slice_key") or ""),
                asset=str(item.get("asset") or "UNKNOWN"),
                strategy_family=str(item.get("strategy_family") or "UNKNOWN"),
                regime=str(item.get("regime") or "UNKNOWN"),
                horizon_hours=int(item.get("horizon_hours") or 0),
                readiness_bucket=str(item.get("readiness_bucket") or "UNKNOWN"),
                confidence_bucket=str(item.get("confidence_bucket") or "UNKNOWN"),
                weekday=str(item.get("weekday") or "UNKNOWN"),
                sample_size=int(item.get("sample_size") or 0),
                favorable_count=int(item.get("favorable_count") or 0),
                unfavorable_count=int(item.get("unfavorable_count") or 0),
                neutral_count=int(item.get("neutral_count") or 0),
                favorable_rate=float(item.get("favorable_rate") or 0.0),
                unfavorable_rate=float(item.get("unfavorable_rate") or 0.0),
                neutral_rate=float(item.get("neutral_rate") or 0.0),
                avg_move_pct=_coerce_float(item.get("avg_move_pct")),
                avg_max_favorable_move_pct=_coerce_float(item.get("avg_max_favorable_move_pct")),
                avg_max_adverse_move_pct=_coerce_float(item.get("avg_max_adverse_move_pct")),
                stability_status=str(item.get("stability_status") or "INSUFFICIENT_SAMPLE"),
                candidate_status=str(item.get("candidate_status") or "BLOCKED"),
                warnings=[str(value) for value in item.get("warnings", []) if str(value).strip()],
            )
        )
    return rows


def _flatten_warning_lists(rows: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for row in rows:
        for warning in row.get("warnings", []):
            warnings.append(str(warning))
    return warnings


def _average(rows: list[dict[str, Any]], key: str) -> float | None:
    values: list[float] = []
    for row in rows:
        value = _coerce_float(row.get(key))
        if value is None:
            continue
        values.append(value)
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _safe_rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 6)


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique_strings(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in unique:
            continue
        unique.append(normalized)
    return unique
