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


class FakeSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response

    def get(self, url: str, params: dict[str, object], timeout: int) -> FakeResponse:
        del url, params, timeout
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_fetch_btc_price_returns_ok_snapshot() -> None:
    service = MarketDataService(
        timeout_seconds=10,
        btc_public_price_url="https://example.com/btc",
        fear_and_greed_url="https://example.com/fng",
        btc_derivatives_symbol="BTCUSDT",
        btc_funding_rate_url="https://example.com/funding",
        btc_open_interest_url="https://example.com/open-interest",
        session=FakeSession(FakeResponse(200, {"symbol": "BTCUSDT", "price": "108000.12"})),
    )

    snapshot = service.fetch_btc_price()

    assert snapshot.status == "OK"
    assert snapshot.value == {"symbol": "BTCUSDT", "price": 108000.12, "quote_currency": "USDT"}


def test_fetch_btc_price_returns_not_available_on_timeout() -> None:
    service = MarketDataService(
        timeout_seconds=10,
        btc_public_price_url="https://example.com/btc",
        fear_and_greed_url="https://example.com/fng",
        btc_derivatives_symbol="BTCUSDT",
        btc_funding_rate_url="https://example.com/funding",
        btc_open_interest_url="https://example.com/open-interest",
        session=FakeSession(requests.Timeout("timed out")),
    )

    snapshot = service.fetch_btc_price()

    assert snapshot.status == "NOT_AVAILABLE"
    assert "timeout" in (snapshot.error_summary or "").lower()


def test_fetch_fear_and_greed_returns_not_available_on_invalid_payload() -> None:
    service = MarketDataService(
        timeout_seconds=10,
        btc_public_price_url="https://example.com/btc",
        fear_and_greed_url="https://example.com/fng",
        btc_derivatives_symbol="BTCUSDT",
        btc_funding_rate_url="https://example.com/funding",
        btc_open_interest_url="https://example.com/open-interest",
        session=FakeSession(FakeResponse(200, {"data": []})),
    )

    snapshot = service.fetch_fear_and_greed()

    assert snapshot.status == "NOT_AVAILABLE"
    assert "unexpected fear & greed payload" in (snapshot.error_summary or "").lower()
