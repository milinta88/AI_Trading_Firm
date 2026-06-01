from __future__ import annotations

from datetime import UTC, datetime

import requests

from core.config import FredSeriesConfig
from services.fred_service import FredService


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
    def __init__(self, response: FakeResponse | Exception | list[FakeResponse | Exception]) -> None:
        self.response = response
        self.calls = 0

    def get(self, url: str, params: dict[str, object], timeout: int) -> FakeResponse:
        del url, params, timeout
        self.calls += 1
        response = self.response
        if isinstance(response, list):
            current = response[min(self.calls - 1, len(response) - 1)]
        else:
            current = response
        if isinstance(current, Exception):
            raise current
        return current


def test_fred_service_returns_not_configured_without_api_key() -> None:
    service = FredService(
        api_key=None,
        base_url="https://example.com/fred",
        timeout_seconds=10,
        series_configs={"gold_us10y": _series_config("gold_us10y", "DGS10", "us10y", "US10Y", 10)},
        session=FakeSession(FakeResponse(200, {})),
    )

    snapshot = service.fetch_gold_macro_snapshots()["gold_us10y"]

    assert snapshot.status == "NOT_CONFIGURED"
    assert "FRED_API_KEY" in (snapshot.error_summary or "")


def test_fred_service_returns_fail_on_invalid_json() -> None:
    service = FredService(
        api_key="fred-key",
        base_url="https://example.com/fred",
        timeout_seconds=10,
        series_configs={"gold_us10y": _series_config("gold_us10y", "DGS10", "us10y", "US10Y", 10)},
        session=FakeSession(FakeResponse(200, {}, json_error=True)),
    )

    snapshot = service.fetch_gold_macro_snapshots()["gold_us10y"]

    assert snapshot.status == "FAIL"
    assert "invalid json" in (snapshot.error_summary or "").lower()


def test_fred_service_marks_old_observation_as_stale() -> None:
    service = FredService(
        api_key="fred-key",
        base_url="https://example.com/fred",
        timeout_seconds=10,
        series_configs={"gold_us10y": _series_config("gold_us10y", "DGS10", "us10y", "US10Y", 10)},
        session=FakeSession(
            FakeResponse(
                200,
                {
                    "observations": [
                        {"date": "2026-01-01", "value": "4.0"},
                        {"date": "2025-12-31", "value": "3.9"},
                    ]
                },
            )
        ),
    )

    snapshot = service.fetch_gold_macro_snapshots()["gold_us10y"]

    assert snapshot.status == "STALE"
    assert snapshot.value["direction"] == "rising"


def test_fred_service_retries_http_429_before_fail() -> None:
    session = FakeSession(
        [
            FakeResponse(429, {}),
            FakeResponse(429, {}),
            FakeResponse(429, {}),
        ]
    )
    sleep_calls: list[float] = []
    service = FredService(
        api_key="fred-key",
        base_url="https://example.com/fred",
        timeout_seconds=10,
        series_configs={"gold_fed_funds": _series_config("gold_fed_funds", "FEDFUNDS", "fed_funds", "Fed Funds", 75)},
        session=session,
        sleep_func=lambda seconds: sleep_calls.append(seconds),
    )

    snapshot = service.fetch_gold_macro_snapshots()["gold_fed_funds"]

    assert snapshot.status == "FAIL"
    assert "HTTP 429" in (snapshot.error_summary or "")
    assert session.calls == 3
    assert sleep_calls == [0.5, 1.0]
    assert "fred-key" not in (snapshot.error_summary or "")


def test_fred_service_cpi_within_75_days_is_not_stale() -> None:
    service = FredService(
        api_key="fred-key",
        base_url="https://example.com/fred",
        timeout_seconds=10,
        series_configs={"gold_cpi": _series_config("gold_cpi", "CPIAUCSL", "cpi", "CPI", 75)},
        session=FakeSession(
            FakeResponse(
                200,
                {
                    "observations": [
                        {"date": "2026-04-01", "value": "320.0"},
                        {"date": "2026-03-01", "value": "319.5"},
                    ]
                },
            )
        ),
    )

    snapshot = service.fetch_gold_macro_snapshots()["gold_cpi"]

    assert snapshot.status == "OK"


def test_fred_service_fed_funds_within_75_days_is_not_stale() -> None:
    service = FredService(
        api_key="fred-key",
        base_url="https://example.com/fred",
        timeout_seconds=10,
        series_configs={"gold_fed_funds": _series_config("gold_fed_funds", "FEDFUNDS", "fed_funds", "Fed Funds", 75)},
        session=FakeSession(
            FakeResponse(
                200,
                {
                    "observations": [
                        {"date": "2026-04-01", "value": "4.33"},
                        {"date": "2026-03-01", "value": "4.31"},
                    ]
                },
            )
        ),
    )

    snapshot = service.fetch_gold_macro_snapshots()["gold_fed_funds"]

    assert snapshot.status == "OK"


def test_fred_service_us10y_keeps_shorter_stale_threshold() -> None:
    service = FredService(
        api_key="fred-key",
        base_url="https://example.com/fred",
        timeout_seconds=10,
        series_configs={"gold_us10y": _series_config("gold_us10y", "DGS10", "us10y", "US10Y", 10)},
        session=FakeSession(
            FakeResponse(
                200,
                {
                    "observations": [
                        {"date": "2026-05-01", "value": "4.10"},
                        {"date": "2026-04-30", "value": "4.05"},
                    ]
                },
            )
        ),
    )

    snapshot = service.fetch_gold_macro_snapshots()["gold_us10y"]

    assert snapshot.status == "STALE"


def _series_config(key: str, series_id: str, data_type: str, display_name: str, stale_after_days: int) -> FredSeriesConfig:
    return FredSeriesConfig(
        key=key,
        series_id=series_id,
        data_type=data_type,
        display_name=display_name,
        stale_after_days=stale_after_days,
    )
