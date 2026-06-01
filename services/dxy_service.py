from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from core.config import DxyProviderConfig
from core.models import MarketDataPoint


class DxyService:
    """Read-only DXY quote service for research workflows."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
    STALE_AFTER_HOURS = 72

    def __init__(
        self,
        config: DxyProviderConfig,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()

    def fetch_latest_quote(self) -> MarketDataPoint:
        fetched_at = datetime.now(UTC)

        if not self.config.enabled:
            return self._build_not_configured(
                timestamp=fetched_at,
                message="DXY provider is disabled in config.",
            )

        if self.config.provider != "yahoo_finance":
            return self._build_not_configured(
                timestamp=fetched_at,
                message=f"DXY provider '{self.config.provider}' is not supported yet.",
            )

        if not self.config.symbol:
            return self._build_not_configured(
                timestamp=fetched_at,
                message="DXY provider symbol is blank, so DXY remains read-only but unconfigured.",
            )

        try:
            payload = self._get_json()
            chart = payload.get("chart")
            if not isinstance(chart, dict):
                raise _DxyServiceError("DXY provider returned an invalid chart payload.")

            if chart.get("error"):
                raise _DxyServiceError("DXY provider returned a chart error response.")

            result_list = chart.get("result")
            if not isinstance(result_list, list) or not result_list:
                raise _DxyServiceError("DXY provider returned no chart result rows.")

            result = result_list[0]
            if not isinstance(result, dict):
                raise _DxyServiceError("DXY provider returned an invalid chart result row.")

            meta = result.get("meta")
            if not isinstance(meta, dict):
                raise _DxyServiceError("DXY provider returned chart metadata in an invalid format.")

            latest_value = self._extract_latest_value(result, meta)
            previous_value = self._parse_optional_float(meta.get("chartPreviousClose"))
            if previous_value is None:
                previous_value = self._parse_optional_float(meta.get("previousClose"))

            quote_time = self._parse_timestamp(meta.get("regularMarketTime"))
            if quote_time is None:
                quote_time = self._extract_last_timestamp(result) or fetched_at

            change = None
            if previous_value is not None:
                change = latest_value - previous_value

            status = "OK"
            error_summary = None
            if fetched_at - quote_time > timedelta(hours=self.STALE_AFTER_HOURS):
                status = "STALE"
                error_summary = (
                    "DXY quote is older than the 72-hour freshness threshold for research monitoring."
                )

            return MarketDataPoint(
                key="gold_dxy",
                asset="Gold",
                source=self.config.provider,
                data_type="dxy",
                status=status,
                timestamp=quote_time,
                value={
                    "provider": self.config.provider,
                    "latest_value": latest_value,
                    "previous_value": previous_value,
                    "change": change,
                    "direction": self._direction_for_change(change),
                    "observation_date": quote_time.date().isoformat(),
                    "quote_timestamp": quote_time.isoformat(),
                    "symbol": str(meta.get("symbol") or self.config.symbol),
                    "currency": str(meta.get("currency") or "USD"),
                    "exchange_name": str(meta.get("exchangeName") or "Yahoo Finance"),
                    "data_note": "Research-only public market data; may be delayed and is not broker-grade execution data.",
                },
                error_summary=error_summary,
            )
        except _DxyServiceError as exc:
            return self._build_failure(timestamp=fetched_at, message=exc.message)
        except (TypeError, ValueError) as exc:
            return self._build_failure(
                timestamp=fetched_at,
                message=f"Unexpected DXY payload from {self.config.provider}: {exc}",
            )

    def _get_json(self) -> dict[str, Any]:
        url = f"{self.BASE_URL}/{self.config.symbol}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }
        params = {"interval": "1d", "range": "5d"}

        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.config.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise _DxyServiceError("DXY provider timeout while fetching DXY quote.") from exc
        except requests.RequestException as exc:
            raise _DxyServiceError(f"DXY provider network error while fetching DXY quote: {exc}") from exc

        if response.status_code >= 500:
            raise _DxyServiceError(f"DXY provider unavailable while fetching DXY quote (HTTP {response.status_code}).")
        if response.status_code >= 400:
            raise _DxyServiceError(f"DXY provider rejected the DXY quote request (HTTP {response.status_code}).")

        try:
            payload = response.json()
        except ValueError as exc:
            raise _DxyServiceError("DXY provider returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise _DxyServiceError("DXY provider returned an invalid payload shape.")
        return payload

    def _build_not_configured(self, timestamp: datetime, message: str) -> MarketDataPoint:
        return MarketDataPoint(
            key="gold_dxy",
            asset="Gold",
            source=self.config.provider,
            data_type="dxy",
            status="NOT_CONFIGURED",
            timestamp=timestamp,
            value={"provider": self.config.provider, "symbol": self.config.symbol},
            error_summary=message,
        )

    def _build_failure(self, timestamp: datetime, message: str) -> MarketDataPoint:
        return MarketDataPoint(
            key="gold_dxy",
            asset="Gold",
            source=self.config.provider,
            data_type="dxy",
            status="FAIL",
            timestamp=timestamp,
            value={"provider": self.config.provider, "symbol": self.config.symbol},
            error_summary=message,
        )

    @staticmethod
    def _extract_latest_value(result: dict[str, Any], meta: dict[str, Any]) -> float:
        latest_value = DxyService._parse_optional_float(meta.get("regularMarketPrice"))
        if latest_value is not None:
            return latest_value

        indicators = result.get("indicators")
        if not isinstance(indicators, dict):
            raise _DxyServiceError("DXY provider did not return price indicators.")

        quote_rows = indicators.get("quote")
        if not isinstance(quote_rows, list) or not quote_rows:
            raise _DxyServiceError("DXY provider did not return quote rows.")

        quote = quote_rows[0]
        if not isinstance(quote, dict):
            raise _DxyServiceError("DXY provider quote row is invalid.")

        closes = quote.get("close")
        if not isinstance(closes, list):
            raise _DxyServiceError("DXY provider close series is missing.")

        for close in reversed(closes):
            latest_value = DxyService._parse_optional_float(close)
            if latest_value is not None:
                return latest_value

        raise _DxyServiceError("DXY provider returned no usable close values.")

    @staticmethod
    def _extract_last_timestamp(result: dict[str, Any]) -> datetime | None:
        timestamps = result.get("timestamp")
        if not isinstance(timestamps, list):
            return None
        for timestamp in reversed(timestamps):
            parsed = DxyService._parse_timestamp(timestamp)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if value in {None, "", 0, "0"}:
            return None
        return datetime.fromtimestamp(int(value), UTC)

    @staticmethod
    def _parse_optional_float(value: object) -> float | None:
        if value in {None, ""}:
            return None
        return float(value)

    @staticmethod
    def _direction_for_change(change: float | None) -> str:
        if change is None:
            return "unknown"
        if change > 0:
            return "rising"
        if change < 0:
            return "falling"
        return "flat"


class _DxyServiceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
