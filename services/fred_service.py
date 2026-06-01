from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

import requests

from core.config import FredSeriesConfig
from core.models import MarketDataPoint

logger = logging.getLogger(__name__)


class FredService:
    """Read-only FRED macro data client for Gold research inputs."""

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        timeout_seconds: int,
        series_configs: dict[str, FredSeriesConfig],
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.series_configs = series_configs
        self.session = session or requests.Session()

    def fetch_gold_macro_snapshots(self) -> dict[str, MarketDataPoint]:
        snapshots: dict[str, MarketDataPoint] = {}
        for key, series_config in self.series_configs.items():
            snapshots[key] = self.fetch_latest_observation(series_config)
        return snapshots

    def fetch_latest_observation(self, series_config: FredSeriesConfig) -> MarketDataPoint:
        fetched_at = datetime.now(UTC)

        if not self.api_key:
            return self._build_not_configured_point(
                key=series_config.key,
                data_type=series_config.data_type,
                display_name=series_config.display_name,
                timestamp=fetched_at,
                message="FRED_API_KEY is missing, so this macro source stays read-only but unconfigured.",
            )

        try:
            payload = self._get_json(series_config)
            observations = payload["observations"]
            latest_observation, previous_observation = self._extract_recent_observations(observations)
            latest_date = date.fromisoformat(str(latest_observation["date"]))
            latest_value = float(latest_observation["value"])
            previous_value = float(previous_observation["value"]) if previous_observation else None
            change = latest_value - previous_value if previous_value is not None else None
            age_days = (fetched_at.date() - latest_date).days

            status = "OK"
            error_summary = None
            if age_days > series_config.stale_after_days:
                status = "STALE"
                error_summary = (
                    f"Latest {series_config.display_name} observation is {age_days} days old, "
                    f"which exceeds the {series_config.stale_after_days}-day threshold."
                )

            return MarketDataPoint(
                key=series_config.key,
                asset="Gold",
                source="FRED",
                data_type=series_config.data_type,
                status=status,
                timestamp=datetime.combine(latest_date, datetime.min.time(), tzinfo=UTC),
                value={
                    "series_id": series_config.series_id,
                    "display_name": series_config.display_name,
                    "latest_value": latest_value,
                    "previous_value": previous_value,
                    "change": change,
                    "direction": self._direction_for_change(change),
                    "observation_date": latest_date.isoformat(),
                    "stale_after_days": series_config.stale_after_days,
                },
                error_summary=error_summary,
            )
        except _FredServiceError as exc:
            return self._build_failure_point(
                key=series_config.key,
                data_type=series_config.data_type,
                display_name=series_config.display_name,
                timestamp=fetched_at,
                message=exc.message,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return self._build_failure_point(
                key=series_config.key,
                data_type=series_config.data_type,
                display_name=series_config.display_name,
                timestamp=fetched_at,
                message=f"Unexpected FRED payload for {series_config.display_name}: {exc}",
            )

    def _get_json(self, series_config: FredSeriesConfig) -> dict[str, Any]:
        params = {
            "series_id": series_config.series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 10,
        }

        try:
            response = self.session.get(self.base_url, params=params, timeout=self.timeout_seconds)
        except requests.Timeout as exc:
            raise _FredServiceError(f"FRED timeout while fetching {series_config.display_name}.") from exc
        except requests.RequestException as exc:
            raise _FredServiceError(f"FRED network error while fetching {series_config.display_name}: {exc}") from exc

        if response.status_code >= 500:
            raise _FredServiceError(
                f"FRED API unavailable while fetching {series_config.display_name} (HTTP {response.status_code})."
            )

        if response.status_code >= 400:
            raise _FredServiceError(
                f"FRED API rejected {series_config.display_name} (HTTP {response.status_code})."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise _FredServiceError(f"FRED returned invalid JSON for {series_config.display_name}.") from exc

        if not isinstance(payload, dict):
            raise _FredServiceError(f"FRED returned an invalid payload shape for {series_config.display_name}.")

        return payload

    def _extract_recent_observations(
        self,
        observations: object,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if not isinstance(observations, list):
            raise _FredServiceError("FRED observations payload is missing or invalid.")

        numeric_observations = [
            observation
            for observation in observations
            if isinstance(observation, dict) and str(observation.get("value", ".")).strip() not in {"", "."}
        ]

        if not numeric_observations:
            raise _FredServiceError("FRED returned no usable observations for the configured series.")

        latest = numeric_observations[0]
        previous = numeric_observations[1] if len(numeric_observations) > 1 else None
        return latest, previous

    @staticmethod
    def _direction_for_change(change: float | None) -> str:
        if change is None:
            return "unknown"
        if change > 0:
            return "rising"
        if change < 0:
            return "falling"
        return "flat"

    @staticmethod
    def _build_not_configured_point(
        key: str,
        data_type: str,
        display_name: str,
        timestamp: datetime,
        message: str,
    ) -> MarketDataPoint:
        return MarketDataPoint(
            key=key,
            asset="Gold",
            source="FRED",
            data_type=data_type,
            status="NOT_CONFIGURED",
            timestamp=timestamp,
            value={"display_name": display_name},
            error_summary=message,
        )

    @staticmethod
    def _build_failure_point(
        key: str,
        data_type: str,
        display_name: str,
        timestamp: datetime,
        message: str,
    ) -> MarketDataPoint:
        return MarketDataPoint(
            key=key,
            asset="Gold",
            source="FRED",
            data_type=data_type,
            status="FAIL",
            timestamp=timestamp,
            value={"display_name": display_name},
            error_summary=message,
        )


class _FredServiceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
