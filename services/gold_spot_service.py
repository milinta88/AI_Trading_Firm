from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from core.config import GoldSpotProviderConfig
from core.models import MarketDataPoint


class GoldSpotService:
    """Read-only Gold spot provider wrapper for research workflows."""

    STALE_AFTER_HOURS = 24
    _SUPPORTED_PROVIDERS = {"goldapi_io", "gold_api"}
    _DEFAULT_GOLDAPI_URL = "https://www.goldapi.io/api/XAU/USD"
    _SOURCE_LABEL = "GoldAPI.io"

    def __init__(
        self,
        config: GoldSpotProviderConfig,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()

    def fetch_latest_price(self) -> MarketDataPoint:
        fetched_at = datetime.now(UTC)

        if not self.config.enabled:
            return self._build_not_configured(
                timestamp=fetched_at,
                message="Gold spot provider is disabled in config.",
            )

        if self.config.provider not in self._SUPPORTED_PROVIDERS:
            return self._build_not_configured(
                timestamp=fetched_at,
                message=f"Gold spot provider '{self.config.provider}' is not supported yet.",
            )

        if not self.config.api_key:
            return self._build_not_configured(
                timestamp=fetched_at,
                message=(
                    f"{self.config.api_key_env} is missing, so Gold spot stays read-only but unconfigured."
                ),
            )

        try:
            payload = self._get_json()
            price = self._parse_required_float(payload.get("price"), "price")
            quote_time = self._parse_provider_timestamp(payload.get("timestamp")) or fetched_at
            previous_value = self._parse_optional_float(payload.get("prev_close_price"))
            change = self._parse_optional_float(payload.get("ch"))
            if change is None and previous_value is not None:
                change = price - previous_value

            status = "OK"
            error_summary = None
            if fetched_at - quote_time > timedelta(hours=self.STALE_AFTER_HOURS):
                status = "STALE"
                error_summary = (
                    "Gold spot quote is older than the 24-hour freshness threshold for research monitoring."
                )

            return MarketDataPoint(
                key="gold_spot_price",
                asset="Gold",
                source=self._SOURCE_LABEL,
                data_type="spot_price",
                status=status,
                timestamp=quote_time,
                value={
                    "provider": "goldapi_io",
                    "latest_value": price,
                    "previous_value": previous_value,
                    "change": change,
                    "direction": self._direction_for_change(change),
                    "observation_date": quote_time.date().isoformat(),
                    "quote_timestamp": quote_time.isoformat(),
                    "currency": str(payload.get("currency") or "USD"),
                    "symbol": payload.get("symbol") or "XAU/USD",
                    "bid": self._parse_optional_float(payload.get("bid")),
                    "ask": self._parse_optional_float(payload.get("ask")),
                },
                error_summary=error_summary,
            )
        except _GoldSpotServiceError as exc:
            return self._build_failure(timestamp=fetched_at, message=exc.message)
        except (TypeError, ValueError) as exc:
            return self._build_failure(
                timestamp=fetched_at,
                message=f"Unexpected Gold spot payload from {self.config.provider}: {exc}",
            )

    def _get_json(self) -> dict[str, Any]:
        request_url = self.config.url or self._DEFAULT_GOLDAPI_URL
        headers = {
            "x-access-token": self.config.api_key or "",
            "Content-Type": "application/json",
            "User-Agent": "AI-Trading-Firm/Research-Only",
        }
        try:
            response = self.session.get(
                request_url,
                headers=headers,
                timeout=self.config.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise _GoldSpotServiceError("Gold spot provider timeout while fetching Gold spot price.") from exc
        except requests.RequestException as exc:
            raise _GoldSpotServiceError(
                f"Gold spot provider network error while fetching Gold spot price: {exc}"
            ) from exc

        if response.status_code >= 500:
            raise _GoldSpotServiceError(
                f"Gold spot provider unavailable while fetching Gold spot price (HTTP {response.status_code})."
            )
        if response.status_code >= 400:
            raise _GoldSpotServiceError(
                f"Gold spot provider rejected the Gold spot request (HTTP {response.status_code})."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise _GoldSpotServiceError("Gold spot provider returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise _GoldSpotServiceError("Gold spot provider returned an invalid payload shape.")
        return payload

    def _build_not_configured(self, timestamp: datetime, message: str) -> MarketDataPoint:
        return MarketDataPoint(
            key="gold_spot_price",
            asset="Gold",
            source=self._SOURCE_LABEL,
            data_type="spot_price",
            status="NOT_CONFIGURED",
            timestamp=timestamp,
            value={"provider": "goldapi_io"},
            error_summary=message,
        )

    def _build_failure(self, timestamp: datetime, message: str) -> MarketDataPoint:
        return MarketDataPoint(
            key="gold_spot_price",
            asset="Gold",
            source=self._SOURCE_LABEL,
            data_type="spot_price",
            status="FAIL",
            timestamp=timestamp,
            value={"provider": "goldapi_io"},
            error_summary=message,
        )

    @staticmethod
    def _parse_provider_timestamp(value: object) -> datetime | None:
        if value in {None, "", 0, "0"}:
            return None
        return datetime.fromtimestamp(int(value), UTC)

    @staticmethod
    def _parse_required_float(value: object, field_name: str) -> float:
        if value in {None, ""}:
            raise ValueError(f"{field_name} is missing.")
        return float(value)

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


class _GoldSpotServiceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
