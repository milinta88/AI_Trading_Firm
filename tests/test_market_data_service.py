from __future__ import annotations

from datetime import UTC, datetime

import requests

from core.config import DxyProviderConfig, GoldSpotProviderConfig
from services.market_data_service import MarketDataService
from services.dxy_service import DxyService
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

    def get(self, url: str, params: dict[str, object], timeout: int) -> FakeResponse:
        del url, params, timeout
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class GoldProviderSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response

    def get(self, url: str, headers: dict[str, str], timeout: int) -> FakeResponse:
        del url, headers, timeout
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class DxyProviderSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response

    def get(self, url: str, params: dict[str, str], headers: dict[str, str], timeout: int) -> FakeResponse:
        del url, params, headers, timeout
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


def test_collect_market_data_keeps_running_when_gold_providers_fail() -> None:
    service = MarketDataService(
        timeout_seconds=10,
        btc_public_price_url="https://example.com/btc",
        fear_and_greed_url="https://example.com/fng",
        btc_derivatives_symbol="BTCUSDT",
        btc_funding_rate_url="https://example.com/funding",
        btc_open_interest_url="https://example.com/open-interest",
        gold_spot_service=GoldSpotService(
            config=GoldSpotProviderConfig(
                enabled=True,
                provider="goldapi_io",
                url="https://example.com/gold",
                api_key_env="GOLD_API_KEY",
                api_key="test-key",
                timeout_seconds=10,
            ),
            session=GoldProviderSession(requests.RequestException("gold down")),
        ),
        dxy_service=DxyService(
            config=DxyProviderConfig(
                enabled=True,
                provider="yahoo_finance",
                symbol="DX-Y.NYB",
                timeout_seconds=10,
            ),
            session=DxyProviderSession(requests.RequestException("dxy down")),
        ),
        session=FakeSession(FakeResponse(200, {"symbol": "BTCUSDT", "price": "108000.12"})),
    )

    snapshots = service.collect_market_data()

    assert snapshots["btc_price"].status == "OK"
    assert snapshots["gold_dxy"].status == "FAIL"
    assert snapshots["gold_spot_price"].status == "FAIL"
    assert len(snapshots) == 10
