from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


EXPECTED_MARKET_TYPES = [
    ("BTC", "price"),
    ("BTC", "fear_and_greed_index"),
    ("BTC", "funding_rate"),
    ("BTC", "open_interest"),
    ("Gold", "us10y"),
    ("Gold", "real_yield"),
    ("Gold", "fed_funds"),
    ("Gold", "cpi"),
    ("Gold", "dxy"),
    ("Gold", "gold_spot_price"),
]


@dataclass(frozen=True)
class DataHygieneCheck:
    check_name: str
    status: str
    details: str
    suggested_action: str


@dataclass(frozen=True)
class DataHygieneReport:
    overall_status: str
    summary: dict[str, Any]
    status_distribution: list[dict[str, Any]]
    checks: list[DataHygieneCheck]


class DataHygieneAnalyzer:
    """Read-only data quality checks over persisted SQLite snapshots."""

    def __init__(
        self,
        database_path: Path,
        now: datetime | None = None,
        stale_after_hours: int = 48,
        gap_warning_hours: int = 48,
    ) -> None:
        self.database_path = database_path
        self.now = now or datetime.now(UTC)
        self.stale_after_hours = stale_after_hours
        self.gap_warning_hours = gap_warning_hours

    def analyze(self) -> DataHygieneReport:
        if not self.database_path.exists():
            return self._not_available_report(f"Database not found at {self.database_path}.")

        try:
            with self._connect_read_only() as connection:
                checks = [
                    self._check_duplicate_snapshots(connection),
                    self._check_missing_recent_market_data(connection),
                    self._check_status_distribution(connection),
                    self._check_data_gaps(connection),
                    self._check_null_or_empty_values(connection),
                ]
                status_distribution = self._status_distribution(connection)
                summary = self._summary(connection, checks)
        except sqlite3.Error as exc:
            return self._not_available_report(f"Unable to read SQLite for data hygiene: {exc}")

        return DataHygieneReport(
            overall_status=_aggregate_check_status(checks),
            summary=summary,
            status_distribution=status_distribution,
            checks=checks,
        )

    def _check_duplicate_snapshots(self, connection: sqlite3.Connection) -> DataHygieneCheck:
        duplicate_details: list[str] = []
        if _table_exists(connection, "market_snapshots"):
            rows = connection.execute(
                """
                SELECT timestamp, asset, data_type, source, COUNT(*) AS duplicate_count
                FROM market_snapshots
                GROUP BY timestamp, asset, data_type, source
                HAVING COUNT(*) > 1
                ORDER BY duplicate_count DESC
                LIMIT 10
                """
            ).fetchall()
            duplicate_details.extend(
                f"market {row['asset']} {row['data_type']} from {row['source']} at {row['timestamp']} appears {row['duplicate_count']} times"
                for row in rows
            )

        if _table_exists(connection, "score_snapshots"):
            rows = connection.execute(
                """
                SELECT timestamp, asset, COUNT(*) AS duplicate_count
                FROM score_snapshots
                GROUP BY timestamp, asset
                HAVING COUNT(*) > 1
                ORDER BY duplicate_count DESC
                LIMIT 10
                """
            ).fetchall()
            duplicate_details.extend(
                f"score {row['asset']} at {row['timestamp']} appears {row['duplicate_count']} times"
                for row in rows
            )

        if duplicate_details:
            return DataHygieneCheck(
                check_name="Duplicate snapshots",
                status="WARNING",
                details="; ".join(duplicate_details),
                suggested_action="Review duplicate rows before adding any future compaction policy. Phase 1.9 does not delete data automatically.",
            )

        return DataHygieneCheck(
            check_name="Duplicate snapshots",
            status="PASS",
            details="No duplicate market or score snapshots found using practical timestamp/asset/type/source keys.",
            suggested_action="No action needed.",
        )

    def _check_missing_recent_market_data(self, connection: sqlite3.Connection) -> DataHygieneCheck:
        if not _table_exists(connection, "market_snapshots"):
            return DataHygieneCheck(
                check_name="Missing recent market data",
                status="NOT_AVAILABLE",
                details="market_snapshots table is not available.",
                suggested_action="Run python main.py --dry-run to create persisted snapshots.",
            )

        issues: list[str] = []
        for asset, data_type in EXPECTED_MARKET_TYPES:
            row = connection.execute(
                """
                SELECT timestamp, status
                FROM market_snapshots
                WHERE asset = ? AND data_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (asset, data_type),
            ).fetchone()
            if row is None:
                issues.append(f"{asset} {data_type}: no persisted snapshot")
                continue

            status = str(row["status"])
            if status in {"FAIL", "NOT_AVAILABLE", "STALE"}:
                issues.append(f"{asset} {data_type}: latest status is {status}")

            timestamp = _parse_datetime(row["timestamp"])
            if timestamp and _age_hours(self.now, timestamp) > self.stale_after_hours:
                issues.append(f"{asset} {data_type}: latest snapshot is older than {self.stale_after_hours} hours")

        if issues:
            return DataHygieneCheck(
                check_name="Missing recent market data",
                status="WARNING",
                details="; ".join(issues),
                suggested_action="Run the daily brief workflow and confirm read-only data sources are available. Do not fake missing values.",
            )

        return DataHygieneCheck(
            check_name="Missing recent market data",
            status="PASS",
            details="Expected market data types have recent persisted snapshots or intentional non-trading statuses.",
            suggested_action="No action needed.",
        )

    def _check_status_distribution(self, connection: sqlite3.Connection) -> DataHygieneCheck:
        distribution = self._status_distribution(connection)
        if not distribution:
            return DataHygieneCheck(
                check_name="Market status distribution",
                status="NOT_AVAILABLE",
                details="No market snapshot statuses are available.",
                suggested_action="Run python main.py --dry-run to populate market snapshots.",
            )

        counts = {row["status"]: int(row["count"]) for row in distribution}
        risky_count = sum(counts.get(status, 0) for status in ("FAIL", "STALE", "NOT_AVAILABLE"))
        details = ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
        if risky_count:
            return DataHygieneCheck(
                check_name="Market status distribution",
                status="WARNING",
                details=details,
                suggested_action="Review failed, stale, or unavailable read-only sources. The brief should continue running safely.",
            )

        return DataHygieneCheck(
            check_name="Market status distribution",
            status="PASS",
            details=details,
            suggested_action="No action needed.",
        )

    def _check_data_gaps(self, connection: sqlite3.Connection) -> DataHygieneCheck:
        if not _table_exists(connection, "market_snapshots"):
            return DataHygieneCheck(
                check_name="Data gaps",
                status="NOT_AVAILABLE",
                details="market_snapshots table is not available.",
                suggested_action="Run the daily brief workflow to collect snapshots.",
            )

        rows = connection.execute(
            """
            SELECT asset, data_type, timestamp
            FROM market_snapshots
            WHERE status = 'OK'
            ORDER BY asset, data_type, timestamp
            """
        ).fetchall()
        grouped: dict[tuple[str, str], list[datetime]] = {}
        for row in rows:
            timestamp = _parse_datetime(row["timestamp"])
            if timestamp is None:
                continue
            grouped.setdefault((str(row["asset"]), str(row["data_type"])), []).append(timestamp)

        gap_details: list[str] = []
        checked_series = 0
        for (asset, data_type), timestamps in grouped.items():
            if len(timestamps) < 3:
                continue
            checked_series += 1
            max_gap = max(
                (current - previous).total_seconds() / 3600
                for previous, current in zip(timestamps, timestamps[1:])
            )
            if max_gap > self.gap_warning_hours:
                gap_details.append(f"{asset} {data_type}: max OK-snapshot gap is {max_gap:.1f} hours")

        if checked_series == 0:
            return DataHygieneCheck(
                check_name="Data gaps",
                status="NOT_AVAILABLE",
                details="Not enough OK snapshot history to evaluate gaps.",
                suggested_action="Continue running daily briefs to build history.",
            )

        if gap_details:
            return DataHygieneCheck(
                check_name="Data gaps",
                status="WARNING",
                details="; ".join(gap_details),
                suggested_action="Review scheduled runs or source outages. Phase 1.9 keeps all historical rows preserved.",
            )

        return DataHygieneCheck(
            check_name="Data gaps",
            status="PASS",
            details=f"No OK-snapshot gaps above {self.gap_warning_hours} hours across {checked_series} series.",
            suggested_action="No action needed.",
        )

    def _check_null_or_empty_values(self, connection: sqlite3.Connection) -> DataHygieneCheck:
        issues: list[str] = []
        if _table_exists(connection, "market_snapshots"):
            count = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM market_snapshots
                    WHERE status = 'OK'
                      AND (
                        value_json IS NULL
                        OR TRIM(value_json) = ''
                        OR TRIM(value_json) IN ('{}', '[]', 'null')
                      )
                    """
                ).fetchone()[0]
            )
            if count:
                issues.append(f"{count} OK market snapshots have null or empty value_json")

        if _table_exists(connection, "score_snapshots"):
            count = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM score_snapshots
                    WHERE components_json IS NULL OR TRIM(components_json) = ''
                       OR reasons_json IS NULL OR TRIM(reasons_json) = ''
                       OR warnings_json IS NULL OR TRIM(warnings_json) = ''
                    """
                ).fetchone()[0]
            )
            if count:
                issues.append(f"{count} score snapshots have null or empty JSON fields")

        if issues:
            return DataHygieneCheck(
                check_name="Null or empty values",
                status="WARNING",
                details="; ".join(issues),
                suggested_action="Inspect source parsers and snapshot writers. Preserve rows for audit until a future retention policy is approved.",
            )

        return DataHygieneCheck(
            check_name="Null or empty values",
            status="PASS",
            details="No abnormal null or empty persisted values found in OK market snapshots or score JSON fields.",
            suggested_action="No action needed.",
        )

    def _status_distribution(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        if not _table_exists(connection, "market_snapshots"):
            return []
        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM market_snapshots
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
        return [
            {
                "table": "market_snapshots",
                "status": row["status"],
                "count": int(row["count"]),
            }
            for row in rows
        ]

    def _summary(self, connection: sqlite3.Connection, checks: list[DataHygieneCheck]) -> dict[str, Any]:
        warning_count = sum(1 for check in checks if check.status == "WARNING")
        fail_count = sum(1 for check in checks if check.status == "FAIL")
        return {
            "total_market_snapshots": _count_rows(connection, "market_snapshots"),
            "total_score_snapshots": _count_rows(connection, "score_snapshots"),
            "latest_market_snapshot_timestamp": _latest_timestamp(connection, "market_snapshots"),
            "latest_score_snapshot_timestamp": _latest_timestamp(connection, "score_snapshots"),
            "warning_count": warning_count,
            "fail_count": fail_count,
        }

    def _connect_read_only(self) -> sqlite3.Connection:
        uri = f"{self.database_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _not_available_report(message: str) -> DataHygieneReport:
        check = DataHygieneCheck(
            check_name="Data hygiene",
            status="NOT_AVAILABLE",
            details=message,
            suggested_action="Run python main.py --dry-run after database setup.",
        )
        return DataHygieneReport(
            overall_status="NOT_AVAILABLE",
            summary={
                "total_market_snapshots": 0,
                "total_score_snapshots": 0,
                "latest_market_snapshot_timestamp": None,
                "latest_score_snapshot_timestamp": None,
                "warning_count": 0,
                "fail_count": 0,
            },
            status_distribution=[],
            checks=[check],
        )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    if not _table_exists(connection, table_name):
        return 0
    return int(connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def _latest_timestamp(connection: sqlite3.Connection, table_name: str) -> str | None:
    if not _table_exists(connection, table_name):
        return None
    column_name = "timestamp" if table_name in {"market_snapshots", "score_snapshots"} else "created_at"
    row = connection.execute(
        f"SELECT {column_name} FROM {table_name} ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return str(row[column_name]) if row and row[column_name] else None


def _parse_datetime(raw_value: Any) -> datetime | None:
    if isinstance(raw_value, datetime):
        parsed = raw_value
    elif raw_value:
        text = str(raw_value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _age_hours(now: datetime, timestamp: datetime) -> float:
    normalized_now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    return max(0.0, (normalized_now - timestamp).total_seconds() / 3600)


def _aggregate_check_status(checks: list[DataHygieneCheck]) -> str:
    if any(check.status == "FAIL" for check in checks):
        return "FAIL"
    if any(check.status == "WARNING" for check in checks):
        return "WARNING"
    if all(check.status == "NOT_AVAILABLE" for check in checks):
        return "NOT_AVAILABLE"
    return "PASS"
