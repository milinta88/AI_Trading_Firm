from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

from core.config import HypothesisReviewConfig
from core.models import HypothesisReviewSummary


_EVALUATED_STATUSES = {"FAVORABLE", "UNFAVORABLE", "NEUTRAL"}
_CANDIDATE_STATUS_ORDER = {
    "REVIEW_CANDIDATE": 0,
    "NEED_MORE_SAMPLES": 1,
    "FAIL_RATE_THRESHOLD": 2,
    "FAIL_ADVERSE_MOVE": 3,
    "BLOCKED": 4,
}


@dataclass(frozen=True)
class HypothesisReviewFilters:
    asset: str | None = None
    strategy_family: str | None = None
    regime: str | None = None
    horizon_hours: int | None = None
    outcome_status: str | None = None
    readiness_bucket: str | None = None
    hypothesis_status: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class HypothesisReviewAnalyzer:
    """Builds read-only review analytics over persisted hypothesis outcomes."""

    def __init__(
        self,
        *,
        database_path: Path | None,
        config: HypothesisReviewConfig,
        lookback_days: int,
    ) -> None:
        self.database_path = database_path
        self.config = config
        self.lookback_days = lookback_days

    def build_summary(
        self,
        now: datetime | None = None,
        *,
        filters: HypothesisReviewFilters | None = None,
    ) -> HypothesisReviewSummary:
        created_at = now.astimezone(UTC) if now else datetime.now(UTC)
        empty = self._empty_summary(created_at=created_at)

        if not self.config.enabled:
            return self._with_warning(empty, "Hypothesis review analytics are disabled in config.")
        if not self.database_path or not self.database_path.exists():
            return self._with_warning(empty, "SQLite database is not available for hypothesis review analytics.")

        try:
            rows = self.list_outcome_rows(filters=filters, limit=None, now=created_at)
        except sqlite3.Error:
            return self._with_warning(empty, "Unable to read hypothesis review analytics from SQLite.")

        if not rows:
            return self._with_warning(empty, "No persisted strategy hypothesis outcomes are available yet.")

        warnings: list[str] = []
        if any(row["regime"] == "UNKNOWN" for row in rows):
            warnings.append("Some persisted outcome rows could not be joined back to full hypothesis metadata.")
        return summarize_hypothesis_review_rows(
            rows,
            config=self.config,
            lookback_days=self.lookback_days,
            created_at=created_at,
            warnings=warnings,
        )

    def list_outcome_rows(
        self,
        *,
        filters: HypothesisReviewFilters | None = None,
        limit: int | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if not self.database_path or not self.database_path.exists():
            return []

        reference_time = now.astimezone(UTC) if now else datetime.now(UTC)
        filters = filters or HypothesisReviewFilters()

        with self._connect_read_only() as connection:
            if not self._table_exists(connection, "strategy_hypothesis_outcomes"):
                return []
            if not self._table_exists(connection, "strategy_hypotheses"):
                return []
            rows = self._fetch_outcome_rows(connection, reference_time, filters=filters)

        if filters.readiness_bucket:
            requested_bucket = str(filters.readiness_bucket).strip().upper()
            rows = [row for row in rows if str(row.get("readiness_bucket")).upper() == requested_bucket]

        if limit is not None:
            return rows[:limit]
        return rows

    def load_latest_summary(self) -> HypothesisReviewSummary | None:
        if not self.database_path or not self.database_path.exists():
            return None

        try:
            with self._connect_read_only() as connection:
                if not self._table_exists(connection, "hypothesis_review_summaries"):
                    return None
                row = connection.execute(
                    "SELECT * FROM hypothesis_review_summaries ORDER BY id DESC LIMIT 1"
                ).fetchone()
        except sqlite3.Error:
            return None

        return self._row_to_summary(dict(row)) if row else None

    def load_recent_summaries(self, limit: int = 10) -> list[HypothesisReviewSummary]:
        if not self.database_path or not self.database_path.exists():
            return []

        try:
            with self._connect_read_only() as connection:
                if not self._table_exists(connection, "hypothesis_review_summaries"):
                    return []
                rows = connection.execute(
                    "SELECT * FROM hypothesis_review_summaries ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        except sqlite3.Error:
            return []

        return [self._row_to_summary(dict(row)) for row in rows]

    def _fetch_outcome_rows(
        self,
        connection: sqlite3.Connection,
        reference_time: datetime,
        *,
        filters: HypothesisReviewFilters,
    ) -> list[dict[str, Any]]:
        cutoff = (reference_time - timedelta(days=self.lookback_days)).isoformat()
        query = """
            SELECT
                o.*,
                COALESCE(h.regime, 'UNKNOWN') AS regime,
                COALESCE(h.readiness_score, 0) AS readiness_score,
                COALESCE(h.hypothesis_status, 'UNKNOWN') AS hypothesis_status
            FROM strategy_hypothesis_outcomes o
            LEFT JOIN strategy_hypotheses h ON h.id = o.hypothesis_id
            WHERE o.created_at >= ?
        """
        params: list[Any] = [cutoff]

        if filters.asset:
            query += " AND o.asset = ?"
            params.append(filters.asset)
        if filters.strategy_family:
            query += " AND o.strategy_family = ?"
            params.append(filters.strategy_family)
        if filters.regime:
            query += " AND COALESCE(h.regime, 'UNKNOWN') = ?"
            params.append(filters.regime)
        if filters.horizon_hours is not None:
            query += " AND o.horizon_hours = ?"
            params.append(int(filters.horizon_hours))
        if filters.outcome_status:
            query += " AND o.outcome_status = ?"
            params.append(filters.outcome_status)
        if filters.hypothesis_status:
            query += " AND COALESCE(h.hypothesis_status, 'UNKNOWN') = ?"
            params.append(filters.hypothesis_status)
        if filters.start_date:
            start_dt = datetime.combine(filters.start_date, time.min, tzinfo=UTC)
            query += " AND o.created_at >= ?"
            params.append(start_dt.isoformat())
        if filters.end_date:
            end_dt = datetime.combine(filters.end_date + timedelta(days=1), time.min, tzinfo=UTC)
            query += " AND o.created_at < ?"
            params.append(end_dt.isoformat())

        query += " ORDER BY o.id DESC"
        rows = connection.execute(query, tuple(params)).fetchall()
        return [self._normalize_outcome_row(dict(row)) for row in rows]

    def _normalize_outcome_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(row)
        normalized["warnings"] = _json_list(row.get("warnings_json"))
        normalized["readiness_score"] = int(row.get("readiness_score") or 0)
        normalized["horizon_hours"] = int(row.get("horizon_hours") or 0)
        normalized["readiness_bucket"] = _readiness_bucket(normalized.get("readiness_score"), self.config)
        return normalized

    def _empty_summary(self, *, created_at: datetime) -> HypothesisReviewSummary:
        return HypothesisReviewSummary(
            total_outcomes=0,
            evaluated_outcomes=0,
            favorable_count=0,
            unfavorable_count=0,
            neutral_count=0,
            insufficient_followup_count=0,
            blocked_not_evaluated_count=0,
            favorable_rate=0.0,
            unfavorable_rate=0.0,
            neutral_rate=0.0,
            by_asset=[],
            by_strategy_family=[],
            by_regime=[],
            by_horizon=[],
            by_readiness_bucket=[],
            by_hypothesis_status=[],
            avg_move_pct=None,
            avg_max_favorable_move_pct=None,
            avg_max_adverse_move_pct=None,
            warnings=[],
            promoted_candidates=[],
            blocked_candidates=[],
            candidate_progress=[],
            created_at=created_at,
            lookback_days=self.lookback_days,
        )

    @staticmethod
    def _with_warning(summary: HypothesisReviewSummary, warning: str) -> HypothesisReviewSummary:
        return HypothesisReviewSummary(
            total_outcomes=summary.total_outcomes,
            evaluated_outcomes=summary.evaluated_outcomes,
            favorable_count=summary.favorable_count,
            unfavorable_count=summary.unfavorable_count,
            neutral_count=summary.neutral_count,
            insufficient_followup_count=summary.insufficient_followup_count,
            blocked_not_evaluated_count=summary.blocked_not_evaluated_count,
            favorable_rate=summary.favorable_rate,
            unfavorable_rate=summary.unfavorable_rate,
            neutral_rate=summary.neutral_rate,
            by_asset=summary.by_asset,
            by_strategy_family=summary.by_strategy_family,
            by_regime=summary.by_regime,
            by_horizon=summary.by_horizon,
            by_readiness_bucket=summary.by_readiness_bucket,
            by_hypothesis_status=summary.by_hypothesis_status,
            avg_move_pct=summary.avg_move_pct,
            avg_max_favorable_move_pct=summary.avg_max_favorable_move_pct,
            avg_max_adverse_move_pct=summary.avg_max_adverse_move_pct,
            warnings=_unique_strings([*summary.warnings, warning]),
            promoted_candidates=summary.promoted_candidates,
            blocked_candidates=summary.blocked_candidates,
            candidate_progress=summary.candidate_progress,
            created_at=summary.created_at,
            lookback_days=summary.lookback_days,
        )

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
    def _row_to_summary(row: dict[str, Any]) -> HypothesisReviewSummary:
        return HypothesisReviewSummary(
            total_outcomes=int(row.get("total_outcomes") or 0),
            evaluated_outcomes=int(row.get("evaluated_outcomes") or 0),
            favorable_count=int(row.get("favorable_count") or 0),
            unfavorable_count=int(row.get("unfavorable_count") or 0),
            neutral_count=int(row.get("neutral_count") or 0),
            insufficient_followup_count=int(row.get("insufficient_followup_count") or 0),
            blocked_not_evaluated_count=int(row.get("blocked_not_evaluated_count") or 0),
            favorable_rate=float(row.get("favorable_rate") or 0.0),
            unfavorable_rate=float(row.get("unfavorable_rate") or 0.0),
            neutral_rate=float(row.get("neutral_rate") or 0.0),
            by_asset=_json_list_of_dicts(row.get("by_asset_json")),
            by_strategy_family=_json_list_of_dicts(row.get("by_strategy_family_json")),
            by_regime=_json_list_of_dicts(row.get("by_regime_json")),
            by_horizon=_json_list_of_dicts(row.get("by_horizon_json")),
            by_readiness_bucket=_json_list_of_dicts(row.get("by_readiness_bucket_json")),
            by_hypothesis_status=_json_list_of_dicts(row.get("by_hypothesis_status_json")),
            avg_move_pct=_coerce_float(row.get("avg_move_pct")),
            avg_max_favorable_move_pct=_coerce_float(row.get("avg_max_favorable_move_pct")),
            avg_max_adverse_move_pct=_coerce_float(row.get("avg_max_adverse_move_pct")),
            warnings=_json_list(row.get("warnings_json")),
            promoted_candidates=_json_list_of_dicts(row.get("promoted_candidates_json")),
            blocked_candidates=_json_list_of_dicts(row.get("blocked_candidates_json")),
            candidate_progress=_json_list_of_dicts(row.get("candidate_progress_json")),
            created_at=_parse_datetime(row.get("created_at")),
            lookback_days=int(row.get("lookback_days") or 0),
        )


def summarize_hypothesis_review_rows(
    rows: list[dict[str, Any]],
    *,
    config: HypothesisReviewConfig,
    lookback_days: int,
    created_at: datetime | None = None,
    warnings: list[str] | None = None,
) -> HypothesisReviewSummary:
    created_timestamp = created_at.astimezone(UTC) if created_at else datetime.now(UTC)
    normalized_rows = [_normalize_review_row(row, config) for row in rows]
    total_outcomes = len(normalized_rows)
    favorable_count = sum(1 for row in normalized_rows if row["outcome_status"] == "FAVORABLE")
    unfavorable_count = sum(1 for row in normalized_rows if row["outcome_status"] == "UNFAVORABLE")
    neutral_count = sum(1 for row in normalized_rows if row["outcome_status"] == "NEUTRAL")
    insufficient_followup_count = sum(
        1 for row in normalized_rows if row["outcome_status"] == "INSUFFICIENT_FOLLOWUP_DATA"
    )
    blocked_not_evaluated_count = sum(
        1 for row in normalized_rows if row["outcome_status"] == "BLOCKED_NOT_EVALUATED"
    )
    evaluated_outcomes = favorable_count + unfavorable_count + neutral_count

    by_asset = _group_rows(normalized_rows, "asset", lambda row: str(row.get("asset") or "UNKNOWN"))
    by_strategy_family = _group_rows(
        normalized_rows,
        "strategy_family",
        lambda row: str(row.get("strategy_family") or "UNKNOWN"),
    )
    by_regime = _group_rows(normalized_rows, "regime", lambda row: str(row.get("regime") or "UNKNOWN"))
    by_horizon = _group_rows(
        normalized_rows,
        "horizon_hours",
        lambda row: str(int(row.get("horizon_hours") or 0)),
    )
    by_readiness_bucket = _group_rows(
        normalized_rows,
        "readiness_bucket",
        lambda row: str(row.get("readiness_bucket") or "UNKNOWN"),
    )
    by_hypothesis_status = _group_rows(
        normalized_rows,
        "hypothesis_status",
        lambda row: str(row.get("hypothesis_status") or "UNKNOWN"),
    )
    candidate_progress = build_candidate_progress(by_strategy_family, config)
    promoted_candidates = [row for row in candidate_progress if row["candidate_status"] == "REVIEW_CANDIDATE"]
    blocked_candidates = [row for row in candidate_progress if row["candidate_status"] != "REVIEW_CANDIDATE"]

    return HypothesisReviewSummary(
        total_outcomes=total_outcomes,
        evaluated_outcomes=evaluated_outcomes,
        favorable_count=favorable_count,
        unfavorable_count=unfavorable_count,
        neutral_count=neutral_count,
        insufficient_followup_count=insufficient_followup_count,
        blocked_not_evaluated_count=blocked_not_evaluated_count,
        favorable_rate=_safe_rate(favorable_count, evaluated_outcomes),
        unfavorable_rate=_safe_rate(unfavorable_count, evaluated_outcomes),
        neutral_rate=_safe_rate(neutral_count, evaluated_outcomes),
        by_asset=by_asset,
        by_strategy_family=by_strategy_family,
        by_regime=by_regime,
        by_horizon=by_horizon,
        by_readiness_bucket=by_readiness_bucket,
        by_hypothesis_status=by_hypothesis_status,
        avg_move_pct=_average(normalized_rows, "move_pct"),
        avg_max_favorable_move_pct=_average(normalized_rows, "max_favorable_move_pct"),
        avg_max_adverse_move_pct=_average(normalized_rows, "max_adverse_move_pct"),
        warnings=_unique_strings(warnings or []),
        promoted_candidates=promoted_candidates,
        blocked_candidates=blocked_candidates,
        candidate_progress=candidate_progress,
        created_at=created_timestamp,
        lookback_days=lookback_days,
    )


def build_candidate_progress(
    by_strategy_family: list[dict[str, Any]],
    config: HypothesisReviewConfig,
) -> list[dict[str, Any]]:
    progress_rows: list[dict[str, Any]] = []
    for row in by_strategy_family:
        family = str(row.get("strategy_family") or "UNKNOWN")
        asset = str(row.get("asset") or _asset_from_family(family))
        evaluated = int(row.get("evaluated_outcomes") or 0)
        favorable_rate = float(row.get("favorable_rate") or 0.0)
        unfavorable_rate = float(row.get("unfavorable_rate") or 0.0)
        avg_adverse = _coerce_float(row.get("avg_max_adverse_move_pct"))
        adverse_limit = float(config.max_avg_adverse_move_pct_for_candidate.get(asset, float("inf")))
        candidate_status = "REVIEW_CANDIDATE"
        reasons: list[str] = []

        if family.endswith("_NO_TRADE"):
            candidate_status = "BLOCKED"
            reasons.append("No-trade strategy families remain blocked for review progression.")
        elif evaluated < config.min_evaluated_outcomes_for_candidate:
            candidate_status = "NEED_MORE_SAMPLES"
            reasons.append(
                f"{config.min_evaluated_outcomes_for_candidate - evaluated} more evaluated outcomes are needed "
                f"to reach the minimum sample size of {config.min_evaluated_outcomes_for_candidate}."
            )
        elif favorable_rate < config.min_favorable_rate_for_candidate:
            candidate_status = "FAIL_RATE_THRESHOLD"
            reasons.append(
                f"Favorable rate {favorable_rate:.2%} is below the required {config.min_favorable_rate_for_candidate:.2%}."
            )
        if unfavorable_rate > config.max_unfavorable_rate_for_candidate:
            if candidate_status == "REVIEW_CANDIDATE":
                candidate_status = "FAIL_RATE_THRESHOLD"
            reasons.append(
                f"Unfavorable rate {unfavorable_rate:.2%} is above the allowed {config.max_unfavorable_rate_for_candidate:.2%}."
            )
        if avg_adverse is None:
            if candidate_status == "REVIEW_CANDIDATE":
                candidate_status = "BLOCKED"
            reasons.append("Average adverse move is not available yet.")
        elif avg_adverse > adverse_limit:
            candidate_status = "FAIL_ADVERSE_MOVE"
            reasons.append(
                f"Average adverse move {avg_adverse:.2f}% is above the allowed {adverse_limit:.2f}%."
            )

        progress_rows.append(
            {
                "strategy_family": family,
                "asset": asset,
                "evaluated_outcomes": evaluated,
                "required_min_outcomes": config.min_evaluated_outcomes_for_candidate,
                "samples_needed": max(config.min_evaluated_outcomes_for_candidate - evaluated, 0),
                "favorable_rate": favorable_rate,
                "required_favorable_rate": config.min_favorable_rate_for_candidate,
                "unfavorable_rate": unfavorable_rate,
                "max_unfavorable_rate": config.max_unfavorable_rate_for_candidate,
                "avg_adverse_move": avg_adverse,
                "avg_max_adverse_move_pct": avg_adverse,
                "max_allowed_adverse_move": adverse_limit,
                "candidate_status": candidate_status,
                "review_status": candidate_status,
                "reason": "Meets current review thresholds." if not reasons else " ".join(_unique_strings(reasons)),
            }
        )

    return sorted(
        progress_rows,
        key=lambda row: (
            _CANDIDATE_STATUS_ORDER.get(str(row.get("candidate_status")), 99),
            int(row.get("samples_needed") or 0),
            -float(row.get("favorable_rate") or 0.0),
            -int(row.get("evaluated_outcomes") or 0),
            str(row.get("strategy_family") or ""),
        ),
    )


def _group_rows(
    rows: list[dict[str, Any]],
    label_key: str,
    label_fn: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        label = str(label_fn(row) or "UNKNOWN")
        grouped.setdefault(label, []).append(row)

    summary_rows: list[dict[str, Any]] = []
    for label, group_rows in sorted(grouped.items()):
        favorable = sum(1 for row in group_rows if row["outcome_status"] == "FAVORABLE")
        unfavorable = sum(1 for row in group_rows if row["outcome_status"] == "UNFAVORABLE")
        neutral = sum(1 for row in group_rows if row["outcome_status"] == "NEUTRAL")
        evaluated = favorable + unfavorable + neutral
        insufficient = sum(1 for row in group_rows if row["outcome_status"] == "INSUFFICIENT_FOLLOWUP_DATA")
        blocked = sum(1 for row in group_rows if row["outcome_status"] == "BLOCKED_NOT_EVALUATED")
        summary_row = {
            label_key: label if label_key != "horizon_hours" else int(label),
            "total_outcomes": len(group_rows),
            "evaluated_outcomes": evaluated,
            "favorable_count": favorable,
            "unfavorable_count": unfavorable,
            "neutral_count": neutral,
            "insufficient_followup_count": insufficient,
            "blocked_not_evaluated_count": blocked,
            "favorable_rate": _safe_rate(favorable, evaluated),
            "unfavorable_rate": _safe_rate(unfavorable, evaluated),
            "neutral_rate": _safe_rate(neutral, evaluated),
            "avg_move_pct": _average(group_rows, "move_pct"),
            "avg_max_favorable_move_pct": _average(group_rows, "max_favorable_move_pct"),
            "avg_max_adverse_move_pct": _average(group_rows, "max_adverse_move_pct"),
        }
        if label_key == "strategy_family":
            assets = sorted({str(row.get("asset") or "UNKNOWN") for row in group_rows})
            summary_row["asset"] = assets[0] if len(assets) == 1 else ", ".join(assets)
        summary_rows.append(summary_row)
    return summary_rows


def _normalize_review_row(row: dict[str, Any], config: HypothesisReviewConfig) -> dict[str, Any]:
    normalized = dict(row)
    normalized["asset"] = str(normalized.get("asset") or _asset_from_family(str(normalized.get("strategy_family") or "")))
    normalized["regime"] = str(normalized.get("regime") or "UNKNOWN")
    normalized["hypothesis_status"] = str(normalized.get("hypothesis_status") or "UNKNOWN")
    normalized["strategy_family"] = str(normalized.get("strategy_family") or "UNKNOWN")
    normalized["outcome_status"] = str(normalized.get("outcome_status") or "UNKNOWN")
    normalized["readiness_score"] = int(normalized.get("readiness_score") or 0)
    normalized["horizon_hours"] = int(normalized.get("horizon_hours") or 0)
    normalized["readiness_bucket"] = str(
        normalized.get("readiness_bucket") or _readiness_bucket(normalized.get("readiness_score"), config)
    )
    warnings = normalized.get("warnings")
    if isinstance(warnings, list):
        normalized["warnings"] = [str(item) for item in warnings if str(item).strip()]
    else:
        normalized["warnings"] = _json_list(normalized.get("warnings_json"))
    return normalized


def _readiness_bucket(readiness_score: Any, config: HypothesisReviewConfig) -> str:
    try:
        score = int(readiness_score)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if score < config.readiness_buckets.low_below:
        return "LOW"
    if score < config.readiness_buckets.medium_below:
        return "MEDIUM"
    return "HIGH"


def _asset_from_family(family: str) -> str:
    if family.startswith("BTC_"):
        return "BTC"
    if family.startswith("GOLD_"):
        return "Gold"
    return "UNKNOWN"


def _safe_rate(count: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(count / denominator, 6)


def _average(rows: list[dict[str, Any]], key: str) -> float | None:
    values: list[float] = []
    for row in rows:
        raw_value = row.get(key)
        if raw_value is None:
            continue
        try:
            values.append(float(raw_value))
        except (TypeError, ValueError):
            continue
    if not values:
        return None
    return round(sum(values) / len(values), 6)


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


def _json_list_of_dicts(raw_value: Any) -> list[dict[str, Any]]:
    if raw_value in {None, ""}:
        return []
    try:
        parsed = json.loads(str(raw_value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(raw_value: Any) -> datetime | None:
    if raw_value in {None, ""}:
        return None
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is None:
            return raw_value.replace(tzinfo=UTC)
        return raw_value.astimezone(UTC)
    text = str(raw_value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _unique_strings(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in unique:
            continue
        unique.append(normalized)
    return unique
