from __future__ import annotations

from datetime import UTC, datetime

from core.models import DataQualityReport, MarketDataPoint


class DataQualityBot:
    """Evaluates whether read-only market data is healthy enough for reporting."""

    _CRITICAL_KEYS = {"btc_price", "btc_fear_greed"}
    _STALE_THRESHOLDS_MINUTES = {
        "btc_price": 180,
        "btc_fear_greed": 60 * 48,
        "btc_funding_rate": 180,
        "btc_open_interest": 180,
        "gold_us10y": 60 * 24 * 10,
        "gold_real_yield": 60 * 24 * 10,
        "gold_fed_funds": 60 * 24 * 75,
        "gold_cpi": 60 * 24 * 75,
        "gold_dxy": 60 * 24 * 3,
        "gold_spot_price": 60 * 24 * 3,
    }

    def evaluate(
        self,
        market_data: dict[str, MarketDataPoint],
        now: datetime | None = None,
    ) -> DataQualityReport:
        evaluation_time = now or datetime.now(UTC)
        source_statuses: dict[str, str] = {}
        notes: list[str] = []
        critical_issue = False
        noncritical_issue = False

        for key, snapshot in market_data.items():
            source_label = self._label_for_snapshot(snapshot)
            status = self._derive_source_status(key=key, snapshot=snapshot, now=evaluation_time)
            source_statuses[source_label] = status

            if status == "OK":
                continue

            note = self._note_for_status(source_label=source_label, status=status, snapshot=snapshot)
            notes.append(note)

            if key in self._CRITICAL_KEYS and status in {"FAIL", "STALE"}:
                critical_issue = True
            else:
                noncritical_issue = True

        if critical_issue:
            overall_status = "FAIL"
        elif noncritical_issue:
            overall_status = "WARNING"
        else:
            overall_status = "PASS"
            notes.append("All enabled read-only market data sources are healthy for reporting.")

        return DataQualityReport(
            overall_status=overall_status,
            source_statuses=source_statuses,
            notes=notes,
        )

    def _derive_source_status(self, key: str, snapshot: MarketDataPoint, now: datetime) -> str:
        if snapshot.status == "OK":
            threshold_minutes = self._threshold_minutes_for_snapshot(key=key, snapshot=snapshot)
            if threshold_minutes is None:
                return "OK"

            age_seconds = (now - snapshot.timestamp).total_seconds()
            if age_seconds > threshold_minutes * 60:
                return "STALE"
            return "OK"

        if snapshot.status == "NOT_CONFIGURED":
            return "NOT_CONFIGURED"

        if snapshot.status == "NOT_AVAILABLE":
            return "FAIL" if key in self._CRITICAL_KEYS else "NOT_AVAILABLE"

        if snapshot.status == "STALE":
            return "STALE"

        return snapshot.status if snapshot.status == "FAIL" else "FAIL"

    def _threshold_minutes_for_snapshot(self, key: str, snapshot: MarketDataPoint) -> int | None:
        if snapshot.source == "FRED" and isinstance(snapshot.value, dict):
            stale_after_days = snapshot.value.get("stale_after_days")
            if stale_after_days not in {None, ""}:
                try:
                    return int(stale_after_days) * 24 * 60
                except (TypeError, ValueError):
                    return self._STALE_THRESHOLDS_MINUTES.get(key)

        return self._STALE_THRESHOLDS_MINUTES.get(key)

    @staticmethod
    def _label_for_snapshot(snapshot: MarketDataPoint) -> str:
        asset_label = snapshot.asset
        data_label = snapshot.data_type.replace("_", " ").title()
        return f"{asset_label} {data_label}"

    @staticmethod
    def _note_for_status(source_label: str, status: str, snapshot: MarketDataPoint) -> str:
        if status == "NOT_CONFIGURED":
            return f"{source_label} is not configured yet. {snapshot.error_summary or ''}".strip()
        if status == "NOT_AVAILABLE":
            return f"{source_label} is unavailable. {snapshot.error_summary or ''}".strip()
        if status == "STALE":
            return f"{source_label} is stale and should be treated cautiously."
        return f"{source_label} is unavailable. {snapshot.error_summary or ''}".strip()
