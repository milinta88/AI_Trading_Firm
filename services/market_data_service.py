from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import requests

from core.models import MarketDataPoint
from services.fred_service import FredService

logger = logging.getLogger(__name__)


class MarketDataService:
    """Read-only market data fetcher for Phase 1.5 research workflows."""

    def __init__(
        self,
        timeout_seconds: int,
        btc_public_price_url: str,
        fear_and_greed_url: str,
        btc_derivatives_symbol: str,
        btc_funding_rate_url: str,
        btc_open_interest_url: str,
        fred_service: FredService | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.btc_public_price_url = btc_public_price_url
        self.fear_and_greed_url = fear_and_greed_url
        self.btc_derivatives_symbol = btc_derivatives_symbol
        self.btc_funding_rate_url = btc_funding_rate_url
        self.btc_open_interest_url = btc_open_interest_url
        self.fred_service = fred_service
        self.session = session or requests.Session()

    def collect_market_data(self) -> dict[str, MarketDataPoint]:
        snapshots = {
            "btc_price": self.fetch_btc_price(),
            "btc_fear_greed": self.fetch_fear_and_greed(),
            "btc_funding_rate": self.fetch_btc_funding_rate(),
            "btc_open_interest": self.fetch_btc_open_interest(),
        }
        snapshots.update(self.fetch_gold_macro_snapshots())

        logger.info("Collected %s market data snapshots.", len(snapshots))
        return snapshots

    def fetch_gold_macro_snapshots(self) -> dict[str, MarketDataPoint]:
        fred_snapshots = (
            self.fred_service.fetch_gold_macro_snapshots()
            if self.fred_service is not None
            else {
                "gold_us10y": self.build_placeholder(
                    key="gold_us10y",
                    asset="Gold",
                    source="FRED",
                    data_type="us10y",
                    message="FRED service is not configured yet.",
                ),
                "gold_real_yield": self.build_placeholder(
                    key="gold_real_yield",
                    asset="Gold",
                    source="FRED",
                    data_type="real_yield",
                    message="FRED service is not configured yet.",
                ),
                "gold_fed_funds": self.build_placeholder(
                    key="gold_fed_funds",
                    asset="Gold",
                    source="FRED",
                    data_type="fed_funds",
                    message="FRED service is not configured yet.",
                ),
                "gold_cpi": self.build_placeholder(
                    key="gold_cpi",
                    asset="Gold",
                    source="FRED",
                    data_type="cpi",
                    message="FRED service is not configured yet.",
                ),
            }
        )

        fred_snapshots["gold_dxy"] = self.build_placeholder(
            key="gold_dxy",
            asset="Gold",
            source="Macro Placeholder",
            data_type="dxy",
            message="DXY live macro data is not configured yet.",
        )
        fred_snapshots["gold_spot_price"] = self.build_placeholder(
            key="gold_spot_price",
            asset="Gold",
            source="Spot Gold Placeholder",
            data_type="spot_price",
            message="Gold spot price integration is not configured yet.",
        )

        return fred_snapshots

    def fetch_btc_price(self) -> MarketDataPoint:
        fetched_at = datetime.now(UTC)
        try:
            payload = self._get_json(
                url=self.btc_public_price_url,
                params={"symbol": "BTCUSDT"},
                source_label="Binance Spot API",
                data_key="btc_price",
            )
            symbol = str(payload["symbol"])
            price = float(payload["price"])
            return MarketDataPoint(
                key="btc_price",
                asset="BTC",
                source="Binance Spot API",
                data_type="price",
                status="OK",
                timestamp=fetched_at,
                value={"symbol": symbol, "price": price, "quote_currency": "USDT"},
            )
        except _MarketDataFetchError as exc:
            return self._build_not_available_point(
                key="btc_price",
                asset="BTC",
                source="Binance Spot API",
                data_type="price",
                fetched_at=fetched_at,
                error_summary=exc.message,
            )
        except (KeyError, TypeError, ValueError) as exc:
            message = f"Unexpected BTC price payload: {exc}"
            logger.warning("%s", message)
            return self._build_not_available_point(
                key="btc_price",
                asset="BTC",
                source="Binance Spot API",
                data_type="price",
                fetched_at=fetched_at,
                error_summary=message,
            )

    def fetch_fear_and_greed(self) -> MarketDataPoint:
        fetched_at = datetime.now(UTC)
        try:
            payload = self._get_json(
                url=self.fear_and_greed_url,
                params={"limit": 1},
                source_label="Alternative.me",
                data_key="btc_fear_greed",
            )
            items = payload["data"]
            latest = items[0]
            value = int(latest["value"])
            classification = str(latest["value_classification"])
            timestamp = datetime.fromtimestamp(int(latest["timestamp"]), UTC)
            return MarketDataPoint(
                key="btc_fear_greed",
                asset="BTC",
                source="Alternative.me",
                data_type="fear_and_greed_index",
                status="OK",
                timestamp=timestamp,
                value={
                    "value": value,
                    "classification": classification,
                    "time_until_update": latest.get("time_until_update"),
                },
            )
        except _MarketDataFetchError as exc:
            return self._build_not_available_point(
                key="btc_fear_greed",
                asset="BTC",
                source="Alternative.me",
                data_type="fear_and_greed_index",
                fetched_at=fetched_at,
                error_summary=exc.message,
            )
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            message = f"Unexpected Fear & Greed payload: {exc}"
            logger.warning("%s", message)
            return self._build_not_available_point(
                key="btc_fear_greed",
                asset="BTC",
                source="Alternative.me",
                data_type="fear_and_greed_index",
                fetched_at=fetched_at,
                error_summary=message,
            )

    def fetch_btc_funding_rate(self) -> MarketDataPoint:
        fetched_at = datetime.now(UTC)
        try:
            payload = self._get_json(
                url=self.btc_funding_rate_url,
                params={"symbol": self.btc_derivatives_symbol},
                source_label="Binance USD-M Futures API",
                data_key="btc_funding_rate",
            )
            symbol = str(payload["symbol"])
            funding_rate = float(payload["lastFundingRate"])
            response_time = self._parse_timestamp(payload.get("time"), fetched_at)
            next_funding_time = self._parse_optional_timestamp(payload.get("nextFundingTime"))

            value = {
                "symbol": symbol,
                "funding_rate": funding_rate,
                "mark_price": self._parse_optional_float(payload.get("markPrice")),
                "index_price": self._parse_optional_float(payload.get("indexPrice")),
                "interest_rate": self._parse_optional_float(payload.get("interestRate")),
                "next_funding_time": next_funding_time.isoformat() if next_funding_time else None,
            }
            return MarketDataPoint(
                key="btc_funding_rate",
                asset="BTC",
                source="Binance USD-M Futures API",
                data_type="funding_rate",
                status="OK",
                timestamp=response_time,
                value=value,
            )
        except _MarketDataFetchError as exc:
            return self._build_not_available_point(
                key="btc_funding_rate",
                asset="BTC",
                source="Binance USD-M Futures API",
                data_type="funding_rate",
                fetched_at=fetched_at,
                error_summary=exc.message,
            )
        except (KeyError, TypeError, ValueError) as exc:
            message = f"Unexpected BTC funding-rate payload: {exc}"
            logger.warning("%s", message)
            return self._build_not_available_point(
                key="btc_funding_rate",
                asset="BTC",
                source="Binance USD-M Futures API",
                data_type="funding_rate",
                fetched_at=fetched_at,
                error_summary=message,
            )

    def fetch_btc_open_interest(self) -> MarketDataPoint:
        fetched_at = datetime.now(UTC)
        try:
            payload = self._get_json(
                url=self.btc_open_interest_url,
                params={"symbol": self.btc_derivatives_symbol},
                source_label="Binance USD-M Futures API",
                data_key="btc_open_interest",
            )
            symbol = str(payload["symbol"])
            open_interest = float(payload["openInterest"])
            response_time = self._parse_timestamp(payload.get("time"), fetched_at)

            return MarketDataPoint(
                key="btc_open_interest",
                asset="BTC",
                source="Binance USD-M Futures API",
                data_type="open_interest",
                status="OK",
                timestamp=response_time,
                value={
                    "symbol": symbol,
                    "open_interest": open_interest,
                },
            )
        except _MarketDataFetchError as exc:
            return self._build_not_available_point(
                key="btc_open_interest",
                asset="BTC",
                source="Binance USD-M Futures API",
                data_type="open_interest",
                fetched_at=fetched_at,
                error_summary=exc.message,
            )
        except (KeyError, TypeError, ValueError) as exc:
            message = f"Unexpected BTC open-interest payload: {exc}"
            logger.warning("%s", message)
            return self._build_not_available_point(
                key="btc_open_interest",
                asset="BTC",
                source="Binance USD-M Futures API",
                data_type="open_interest",
                fetched_at=fetched_at,
                error_summary=message,
            )

    def build_placeholder(
        self,
        key: str,
        asset: str,
        source: str,
        data_type: str,
        message: str,
    ) -> MarketDataPoint:
        return MarketDataPoint(
            key=key,
            asset=asset,
            source=source,
            data_type=data_type,
            status="NOT_CONFIGURED",
            timestamp=datetime.now(UTC),
            value=None,
            error_summary=message,
        )

    def _build_not_available_point(
        self,
        key: str,
        asset: str,
        source: str,
        data_type: str,
        fetched_at: datetime,
        error_summary: str,
    ) -> MarketDataPoint:
        return MarketDataPoint(
            key=key,
            asset=asset,
            source=source,
            data_type=data_type,
            status="NOT_AVAILABLE",
            timestamp=fetched_at,
            value=None,
            error_summary=error_summary,
        )

    def _get_json(
        self,
        url: str,
        params: dict[str, Any],
        source_label: str,
        data_key: str,
    ) -> dict[str, Any]:
        try:
            response = self.session.get(url, params=params, timeout=self.timeout_seconds)
        except requests.Timeout as exc:
            raise _MarketDataFetchError(f"{source_label} timeout while fetching {data_key}.") from exc
        except requests.RequestException as exc:
            raise _MarketDataFetchError(f"{source_label} network error while fetching {data_key}: {exc}") from exc

        if response.status_code >= 500:
            raise _MarketDataFetchError(
                f"{source_label} unavailable while fetching {data_key} (HTTP {response.status_code})."
            )

        if response.status_code >= 400:
            raise _MarketDataFetchError(
                f"{source_label} rejected {data_key} request (HTTP {response.status_code})."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise _MarketDataFetchError(f"{source_label} returned invalid JSON for {data_key}.") from exc

        if not isinstance(payload, dict):
            raise _MarketDataFetchError(f"{source_label} returned an invalid payload shape for {data_key}.")

        return payload

    @staticmethod
    def _parse_timestamp(value: object, fallback: datetime) -> datetime:
        if value is None:
            return fallback
        return datetime.fromtimestamp(int(value) / 1000, UTC)

    @staticmethod
    def _parse_optional_timestamp(value: object) -> datetime | None:
        if value is None or value == "" or value == 0 or value == "0":
            return None
        return datetime.fromtimestamp(int(value) / 1000, UTC)

    @staticmethod
    def _parse_optional_float(value: object) -> float | None:
        if value is None or value == "":
            return None
        return float(value)


class _MarketDataFetchError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
