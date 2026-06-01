from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArchiveQuery:
    start_date: date | None = None
    end_date: date | None = None
    keyword: str | None = None
    status: str | None = None
    limit: int = 50


@dataclass(frozen=True)
class ReportArchiveItem:
    item_type: str
    workflow_run_id: int | None
    run_date: str | None
    status: str | None
    created_at: str | None
    completed_at: str | None
    channel: str | None
    recipient: str | None
    title: str
    text: str
    summary: str | None
    error_message: str | None


@dataclass(frozen=True)
class ReportArchiveResult:
    database_available: bool
    message: str
    latest_report: ReportArchiveItem | None
    recent_reports: list[ReportArchiveItem]
    recent_messages: list[ReportArchiveItem]
    items: list[ReportArchiveItem]


class ReportArchive:
    """Read-only loader for persisted daily reports and outbound message logs."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def load(self, query: ArchiveQuery | None = None) -> ReportArchiveResult:
        effective_query = query or ArchiveQuery()
        if not self.database_path.exists():
            return ReportArchiveResult(
                database_available=False,
                message=f"Database not found at {self.database_path}.",
                latest_report=None,
                recent_reports=[],
                recent_messages=[],
                items=[],
            )

        try:
            with self._connect_read_only() as connection:
                reports = self._fetch_reports(connection)
                messages = self._fetch_messages(connection)
        except sqlite3.Error as exc:
            return ReportArchiveResult(
                database_available=False,
                message=f"Unable to read report archive: {exc}",
                latest_report=None,
                recent_reports=[],
                recent_messages=[],
                items=[],
            )

        filtered_reports = filter_archive_items(reports, effective_query)
        filtered_messages = filter_archive_items(messages, effective_query)
        all_items = sorted([*filtered_reports, *filtered_messages], key=_item_sort_key, reverse=True)
        limit = max(1, effective_query.limit)
        recent_reports = filtered_reports[:limit]
        recent_messages = filtered_messages[:limit]
        items = all_items[:limit]

        return ReportArchiveResult(
            database_available=True,
            message=f"Loaded report archive from {self.database_path}.",
            latest_report=recent_reports[0] if recent_reports else None,
            recent_reports=recent_reports,
            recent_messages=recent_messages,
            items=items,
        )

    def _fetch_reports(self, connection: sqlite3.Connection) -> list[ReportArchiveItem]:
        if not _table_exists(connection, "workflow_runs"):
            return []

        rows = connection.execute(
            """
            SELECT id, run_date, status, summary, report_text, error_message, created_at, completed_at
            FROM workflow_runs
            WHERE report_text IS NOT NULL AND report_text != ''
            ORDER BY id DESC
            """
        ).fetchall()

        reports: list[ReportArchiveItem] = []
        for row in rows:
            reports.append(
                ReportArchiveItem(
                    item_type="report",
                    workflow_run_id=int(row["id"]),
                    run_date=row["run_date"],
                    status=row["status"],
                    created_at=row["created_at"],
                    completed_at=row["completed_at"],
                    channel=None,
                    recipient=None,
                    title=f"Daily Brief #{row['id']} ({row['run_date']})",
                    text=str(row["report_text"] or ""),
                    summary=row["summary"],
                    error_message=row["error_message"],
                )
            )
        return reports

    def _fetch_messages(self, connection: sqlite3.Connection) -> list[ReportArchiveItem]:
        if not _table_exists(connection, "outbound_messages"):
            return []

        join_clause = "LEFT JOIN workflow_runs w ON w.id = m.workflow_run_id" if _table_exists(connection, "workflow_runs") else ""
        select_run_date = "w.run_date" if join_clause else "NULL"
        rows = connection.execute(
            f"""
            SELECT
                m.id,
                m.workflow_run_id,
                {select_run_date} AS run_date,
                m.channel,
                m.status,
                m.recipient,
                m.message_preview,
                m.error_message,
                m.created_at
            FROM outbound_messages m
            {join_clause}
            ORDER BY m.id DESC
            """
        ).fetchall()

        messages: list[ReportArchiveItem] = []
        for row in rows:
            messages.append(
                ReportArchiveItem(
                    item_type="message",
                    workflow_run_id=int(row["workflow_run_id"]) if row["workflow_run_id"] is not None else None,
                    run_date=row["run_date"],
                    status=row["status"],
                    created_at=row["created_at"],
                    completed_at=None,
                    channel=row["channel"],
                    recipient=row["recipient"],
                    title=f"{str(row['channel']).title()} message #{row['id']}",
                    text=str(row["message_preview"] or ""),
                    summary=None,
                    error_message=row["error_message"],
                )
            )
        return messages

    def _connect_read_only(self) -> sqlite3.Connection:
        uri = f"{self.database_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection


def filter_archive_items(items: list[ReportArchiveItem], query: ArchiveQuery) -> list[ReportArchiveItem]:
    keyword = (query.keyword or "").strip().lower()
    status = (query.status or "").strip().lower()
    if status == "all":
        status = ""

    filtered: list[ReportArchiveItem] = []
    for item in items:
        item_date = _item_date(item)
        if query.start_date and item_date and item_date < query.start_date:
            continue
        if query.end_date and item_date and item_date > query.end_date:
            continue
        if (query.start_date or query.end_date) and item_date is None:
            continue
        if status and str(item.status or "").lower() != status:
            continue
        if keyword and keyword not in _search_text(item):
            continue
        filtered.append(item)

    return sorted(filtered, key=_item_sort_key, reverse=True)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _search_text(item: ReportArchiveItem) -> str:
    parts = [
        item.title,
        item.text,
        item.summary or "",
        item.error_message or "",
        item.status or "",
        item.channel or "",
    ]
    return " ".join(parts).lower()


def _item_date(item: ReportArchiveItem) -> date | None:
    for raw_value in (item.run_date, item.completed_at, item.created_at):
        parsed = _parse_date(raw_value)
        if parsed:
            return parsed
    return None


def _item_sort_key(item: ReportArchiveItem) -> tuple[str, int]:
    timestamp = item.completed_at or item.created_at or item.run_date or ""
    return timestamp, item.workflow_run_id or 0


def _parse_date(raw_value: Any) -> date | None:
    if isinstance(raw_value, datetime):
        return raw_value.date()
    if isinstance(raw_value, date):
        return raw_value
    if not raw_value:
        return None
    text = str(raw_value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
