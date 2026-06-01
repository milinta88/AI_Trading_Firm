from __future__ import annotations

from datetime import UTC, datetime

import requests

from services.market_data_service import MarketDataService


class FakeResponse:
    def __init__(self, status_code: int, payload: object, json_error: bool = False) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self) -> object:
        if self._json_error:
            raise ValueError("bad json")
        return self._payload


class RoutingSession:
    def __init__(self, responses: dict[str, FakeResponse | Exception]) -> None:
        self.responses = responses

    def get(self, url: str, params: dict[str, object], timeout: int) -> FakeResponse:
        del params, timeout
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def test_fetch_btc_funding_rate_returns_ok_snapshot() -> None:
    service = _build_service(
        RoutingSession(
            {
                "https://example.com/funding": FakeResponse(
                    200,
                    {
                        "symbol": "BTCUSDT",
                        "markPrice": "11793.63104562",
                        "indexPrice": "11781.80495970",
                        "lastFundingRate": "0.00038246",
                        "interestRate": "0.00010000",
                        "nextFundingTime": 1597392000000,
                        "time": 1597370495002,
                    },
                )
            }
        )
    )

    snapshot = service.fetch_btc_funding_rate()

    assert snapshot.status == "OK"
    assert snapshot.source == "Binance USD-M Futures API"
    assert snapshot.value == {
        "symbol": "BTCUSDT",
        "funding_rate": 0.00038246,
        "mark_price": 11793.63104562,
        "index_price": 11781.8049597,
        "interest_rate": 0.0001,
        "next_funding_time": "2020-08-14T08:00:00+00:00",
    }
    assert snapshot.timestamp == datetime(2020, 8, 14, 2, 1, 35, 2000, tzinfo=UTC)


def test_fetch_btc_open_interest_returns_ok_snapshot() -> None:
    service = _build_service(
        RoutingSession(
            {
                "https://example.com/open-interest": FakeResponse(
                    200,
                    {
                        "openInterest": "10659.509",
                        "symbol": "BTCUSDT",
                        "time": 1589437530011,
                    },
                )
            }
        )
    )

    snapshot = service.fetch_btc_open_interest()

    assert snapshot.status == "OK"
    assert snapshot.value == {
        "symbol": "BTCUSDT",
        "open_interest": 10659.509,
    }
    assert snapshot.timestamp == datetime(2020, 5, 14, 6, 25, 30, 11000, tzinfo=UTC)


def test_fetch_btc_funding_rate_returns_not_available_on_invalid_payload() -> None:
    service = _build_service(
        RoutingSession(
            {
                "https://example.com/funding": FakeResponse(
                    200,
                    {
                        "symbol": "BTCUSDT",
                    },
                )
            }
        )
    )

    snapshot = service.fetch_btc_funding_rate()

    assert snapshot.status == "NOT_AVAILABLE"
    assert "unexpected btc funding-rate payload" in (snapshot.error_summary or "").lower()


def test_fetch_btc_open_interest_returns_not_available_on_network_error() -> None:
    service = _build_service(
        RoutingSession(
            {
                "https://example.com/open-interest": requests.Timeout("timed out"),
            }
        )
    )

    snapshot = service.fetch_btc_open_interest()

    assert snapshot.status == "NOT_AVAILABLE"
    assert "timeout" in (snapshot.error_summary or "").lower()


def _build_service(session: RoutingSession) -> MarketDataService:
    return MarketDataService(
        timeout_seconds=10,
        btc_public_price_url="https://example.com/btc",
        fear_and_greed_url="https://example.com/fng",
        btc_derivatives_symbol="BTCUSDT",
        btc_funding_rate_url="https://example.com/funding",
        btc_open_interest_url="https://example.com/open-interest",
        session=session,
    )
