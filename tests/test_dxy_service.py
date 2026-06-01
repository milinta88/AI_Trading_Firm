from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from core.config import DxyProviderConfig
from database.init_db import initialize_database
from database.repository import WorkflowRepository
from services.dxy_service import DxyService


class FakeResponse:
    def __init__(self, status_code: int, payload: object, json_error: bool = False) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self) -> object:
        if self._json_error:
            raise ValueError("bad json")
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response

    def get(self, url: str, params: dict[str, str], headers: dict[str, str], timeout: int) -> FakeResponse:
        del url, params, headers, timeout
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_dxy_service_returns_not_configured_when_disabled() -> None:
    service = DxyService(
        config=_config(enabled=False),
        session=FakeSession(FakeResponse(200, {})),
    )

    snapshot = service.fetch_latest_quote()

    assert snapshot.status == "NOT_CONFIGURED"
    assert "disabled" in (snapshot.error_summary or "").lower()


def test_dxy_service_ok_snapshot_can_be_persisted(tmp_path: Path) -> None:
    market_time = int(datetime.now(UTC).timestamp())
    service = DxyService(
        config=_config(enabled=True),
        session=FakeSession(
            FakeResponse(
                200,
                {
                    "chart": {
                        "result": [
                            {
                                "meta": {
                                    "symbol": "DX-Y.NYB",
                                    "regularMarketPrice": 104.12,
                                    "chartPreviousClose": 103.88,
                                    "regularMarketTime": market_time,
                                    "currency": "USD",
                                    "exchangeName": "NYB",
                                },
                                "timestamp": [market_time],
                                "indicators": {"quote": [{"close": [104.12]}]},
                            }
                        ],
                        "error": None,
                    }
                },
            )
        ),
    )

    snapshot = service.fetch_latest_quote()

    assert snapshot.status == "OK"
    assert snapshot.value["latest_value"] == 104.12

    database_path = tmp_path / "data" / "database.db"
    initialize_database(database_path)
    repository = WorkflowRepository(database_path)
    workflow_run_id = repository.create_workflow_run(run_date=datetime.now(UTC).date(), mode="research")
    repository.store_market_snapshot(workflow_run_id, snapshot)

    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT asset, source, data_type, status, value_json
            FROM market_snapshots
            WHERE workflow_run_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (workflow_run_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "Gold"
    assert row[1] == "yahoo_finance"
    assert row[2] == "dxy"
    assert row[3] == "OK"
    assert json.loads(str(row[4]))["latest_value"] == 104.12


def _config(enabled: bool) -> DxyProviderConfig:
    return DxyProviderConfig(
        enabled=enabled,
        provider="yahoo_finance",
        symbol="DX-Y.NYB",
        timeout_seconds=10,
    )
