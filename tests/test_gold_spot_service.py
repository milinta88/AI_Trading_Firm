from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import requests

from core.config import GoldSpotProviderConfig
from database.init_db import initialize_database
from database.repository import WorkflowRepository
from services.gold_spot_service import GoldSpotService


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

    def get(self, url: str, headers: dict[str, str], timeout: int) -> FakeResponse:
        del url, headers, timeout
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_gold_spot_service_returns_not_configured_when_disabled() -> None:
    service = GoldSpotService(
        config=_config(enabled=False, api_key=None, url="https://example.com/gold"),
        session=FakeSession(FakeResponse(200, {})),
    )

    snapshot = service.fetch_latest_price()

    assert snapshot.status == "NOT_CONFIGURED"
    assert "disabled" in (snapshot.error_summary or "").lower()


def test_gold_spot_service_returns_not_configured_without_api_key() -> None:
    service = GoldSpotService(
        config=_config(enabled=True, api_key=None, url="https://example.com/gold"),
        session=FakeSession(FakeResponse(200, {})),
    )

    snapshot = service.fetch_latest_price()

    assert snapshot.status == "NOT_CONFIGURED"
    assert "GOLD_API_KEY" in (snapshot.error_summary or "")


def test_gold_spot_service_ok_snapshot_can_be_persisted(tmp_path: Path) -> None:
    quote_time = int(datetime.now(UTC).timestamp())
    service = GoldSpotService(
        config=_config(enabled=True, api_key="gold-secret", url="https://example.com/gold"),
        session=FakeSession(
            FakeResponse(
                200,
                {
                    "price": 2325.45,
                    "prev_close_price": 2319.10,
                    "timestamp": quote_time,
                    "currency": "USD",
                    "symbol": "XAU/USD",
                },
            )
        ),
    )

    snapshot = service.fetch_latest_price()

    assert snapshot.status == "OK"
    assert snapshot.value["latest_value"] == 2325.45

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
    assert row[1] == "gold_api"
    assert row[2] == "spot_price"
    assert row[3] == "OK"
    assert json.loads(str(row[4]))["latest_value"] == 2325.45


def test_gold_spot_service_failure_does_not_leak_api_key() -> None:
    secret = "super-secret-key"
    service = GoldSpotService(
        config=_config(enabled=True, api_key=secret, url="https://example.com/gold"),
        session=FakeSession(requests.RequestException("provider unavailable")),
    )

    snapshot = service.fetch_latest_price()

    assert snapshot.status == "FAIL"
    assert secret not in (snapshot.error_summary or "")


def _config(enabled: bool, api_key: str | None, url: str) -> GoldSpotProviderConfig:
    return GoldSpotProviderConfig(
        enabled=enabled,
        provider="gold_api",
        url=url,
        api_key_env="GOLD_API_KEY",
        api_key=api_key,
        timeout_seconds=10,
    )
