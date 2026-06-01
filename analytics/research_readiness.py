from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from analytics.trend_analyzer import TrendAnalyzer
from core.config import ResearchReadinessConfig
from core.models import MultiPointTrendResult, ResearchReadinessResult


@dataclass(frozen=True)
class SourceRequirement:
    label: str
    data_type: str
    stale_key: str
    weight: int


class ResearchReadinessAnalyzer:
    """Builds read-only research readiness and regime summaries from persisted snapshots only."""

    BTC_REQUIREMENTS = [
        SourceRequirement("BTC Price", "price", "btc_price", 35),
        SourceRequirement("BTC Fear & Greed", "fear_and_greed_index", "fear_and_greed", 20),
        SourceRequirement("BTC Funding Rate", "funding_rate", "btc_derivatives", 25),
        SourceRequirement("BTC Open Interest", "open_interest", "btc_derivatives", 20),
    ]
    GOLD_REQUIREMENTS = [
        SourceRequirement("Gold US10Y", "us10y", "gold_macro", 25),
        SourceRequirement("Gold Real Yield", "real_yield", "gold_macro", 25),
        SourceRequirement("Gold Fed Funds", "fed_funds", "gold_macro", 15),
        SourceRequirement("Gold CPI", "cpi", "gold_macro", 15),
        SourceRequirement("Gold DXY", "dxy", "gold_macro", 10),
        SourceRequirement("Gold Spot Price", "spot_price", "gold_macro", 10),
    ]

    def __init__(self, database_path: Path, config: ResearchReadinessConfig) -> None:
        self.database_path = database_path
        self.config = config
        self.trend_analyzer = TrendAnalyzer(
            database_path=database_path,
            lookback_points=max(5, config.min_snapshots_for_regime),
        )

    def analyze_all(self) -> dict[str, ResearchReadinessResult]:
        if not self.config.enabled:
            return {
                "BTC": self._disabled_result("BTC"),
                "Gold": self._disabled_result("Gold"),
            }

        if not self.database_path.exists():
            return {
                "BTC": self._not_available_result("BTC", f"Database not found at {self.database_path}."),
                "Gold": self._not_available_result("Gold", f"Database not found at {self.database_path}."),
            }

        multipoint_trends = self.trend_analyzer.analyze_all_multipoint(
            lookback_points=self.config.min_snapshots_for_regime
        )
        try:
            with self._connect_read_only() as connection:
                if not self._table_exists(connection, "market_snapshots"):
                    return {
                        "BTC": self._not_available_result("BTC", "market_snapshots table is not available."),
                        "Gold": self._not_available_result("Gold", "market_snapshots table is not available."),
                    }
                latest_rows = self._fetch_latest_market_rows(connection)
                return {
                    "BTC": self._analyze_btc(latest_rows, multipoint_trends),
                    "Gold": self._analyze_gold(latest_rows, multipoint_trends),
                }
        except sqlite3.Error as exc:
            message = f"Unable to read research readiness from SQLite: {exc}"
            return {
                "BTC": self._failure_result("BTC", message),
                "Gold": self._failure_result("Gold", message),
            }

    def _analyze_btc(
        self,
        latest_rows: dict[tuple[str, str], dict[str, str]],
        multipoint_trends: dict[str, MultiPointTrendResult],
    ) -> ResearchReadinessResult:
        data_completeness, stale_sources, missing_sources, warnings = self._evaluate_sources(
            asset="BTC",
            requirements=self.BTC_REQUIREMENTS,
            latest_rows=latest_rows,
        )
        price_trend = multipoint_trends.get("btc_price")
        funding_trend = multipoint_trends.get("btc_funding_rate")
        open_interest_trend = multipoint_trends.get("btc_open_interest")
        regime = self._classify_btc_regime(price_trend)

        if regime == "HIGH_VOLATILITY":
            warnings.append("BTC is in a HIGH_VOLATILITY regime; treat research conclusions cautiously.")

        if funding_trend and funding_trend.status != "OK":
            warnings.append("BTC funding-rate history is still limited for multipoint regime context.")
        if open_interest_trend and open_interest_trend.status != "OK":
            warnings.append("BTC open-interest history is still limited for multipoint regime context.")

        readiness_score = self._calculate_readiness_score(data_completeness, regime)
        no_trade_reasons = self._build_no_trade_reasons(
            asset="BTC",
            regime=regime,
            readiness_score=readiness_score,
            stale_sources=stale_sources,
            missing_sources=missing_sources,
        )

        return ResearchReadinessResult(
            asset="BTC",
            readiness_score=readiness_score,
            regime=regime,
            data_completeness=data_completeness,
            stale_sources=stale_sources,
            missing_sources=missing_sources,
            warnings=warnings,
            decision_ready=not no_trade_reasons,
            no_trade_reasons=no_trade_reasons,
        )

    def _analyze_gold(
        self,
        latest_rows: dict[tuple[str, str], dict[str, str]],
        multipoint_trends: dict[str, MultiPointTrendResult],
    ) -> ResearchReadinessResult:
        data_completeness, stale_sources, missing_sources, warnings = self._evaluate_sources(
            asset="Gold",
            requirements=self.GOLD_REQUIREMENTS,
            latest_rows=latest_rows,
        )
        us10y_trend = multipoint_trends.get("gold_us10y")
        real_yield_trend = multipoint_trends.get("gold_real_yield")
        regime = self._classify_gold_regime(us10y_trend, real_yield_trend)

        if regime == "MIXED":
            warnings.append("Gold macro regime is MIXED; conviction is reduced until rates signals align.")

        if multipoint_trends.get("gold_fed_funds") and multipoint_trends["gold_fed_funds"].status != "OK":
            warnings.append("Gold Fed Funds trend remains contextual because persisted history is still limited.")
        if multipoint_trends.get("gold_cpi") and multipoint_trends["gold_cpi"].status != "OK":
            warnings.append("Gold CPI trend remains contextual because persisted history is still limited.")

        readiness_score = self._calculate_readiness_score(data_completeness, regime)
        no_trade_reasons = self._build_no_trade_reasons(
            asset="Gold",
            regime=regime,
            readiness_score=readiness_score,
            stale_sources=stale_sources,
            missing_sources=missing_sources,
        )

        return ResearchReadinessResult(
            asset="Gold",
            readiness_score=readiness_score,
            regime=regime,
            data_completeness=data_completeness,
            stale_sources=stale_sources,
            missing_sources=missing_sources,
            warnings=warnings,
            decision_ready=not no_trade_reasons,
            no_trade_reasons=no_trade_reasons,
        )

    def _evaluate_sources(
        self,
        asset: str,
        requirements: list[SourceRequirement],
        latest_rows: dict[tuple[str, str], dict[str, str]],
    ) -> tuple[int, list[str], list[str], list[str]]:
        completeness_score = 0
        stale_sources: list[str] = []
        missing_sources: list[str] = []
        warnings: list[str] = []

        for requirement in requirements:
            row = latest_rows.get((asset, requirement.data_type))
            if row is None:
                missing_sources.append(requirement.label)
                warnings.append(f"{requirement.label} has no persisted market snapshot yet.")
                continue

            status = str(row.get("status") or "NOT_AVAILABLE")
            if status in {"NOT_CONFIGURED", "NOT_AVAILABLE", "FAIL"}:
                missing_sources.append(requirement.label)
                detail = str(row.get("error_summary") or "").strip()
                if detail:
                    warnings.append(f"{requirement.label}: {detail}")
                continue

            if status == "STALE" or self._timestamp_is_stale(row, requirement.stale_key):
                stale_sources.append(requirement.label)
                detail = str(row.get("error_summary") or "").strip()
                if detail:
                    warnings.append(f"{requirement.label}: {detail}")
                else:
                    warnings.append(
                        f"{requirement.label} is older than the configured {requirement.stale_key} freshness window."
                    )
                continue

            if status == "OK":
                completeness_score += requirement.weight
                continue

            missing_sources.append(requirement.label)
            warnings.append(f"{requirement.label} has unexpected status {status}.")

        return int(min(100, completeness_score)), stale_sources, missing_sources, warnings

    def _classify_btc_regime(self, price_trend: MultiPointTrendResult | None) -> str:
        if (
            price_trend is None
            or price_trend.status != "OK"
            or price_trend.lookback_points < self.config.min_snapshots_for_regime
        ):
            return "INSUFFICIENT_DATA"

        range_pct = self._range_pct(price_trend)
        if price_trend.direction == "rising" and price_trend.trend_strength in {"moderate", "strong"}:
            return "TREND_UP"
        if price_trend.direction == "falling" and price_trend.trend_strength in {"moderate", "strong"}:
            return "TREND_DOWN"
        if price_trend.direction in {"mixed", "flat"} and range_pct >= 8:
            return "HIGH_VOLATILITY"
        if range_pct >= 10:
            return "HIGH_VOLATILITY"
        return "RANGE"

    def _classify_gold_regime(
        self,
        us10y_trend: MultiPointTrendResult | None,
        real_yield_trend: MultiPointTrendResult | None,
    ) -> str:
        if not self._trend_ready_for_regime(us10y_trend) or not self._trend_ready_for_regime(real_yield_trend):
            return "INSUFFICIENT_DATA"

        supportive_signals = 0
        pressure_signals = 0
        for trend in (us10y_trend, real_yield_trend):
            if trend.direction == "falling":
                supportive_signals += 1
            elif trend.direction == "rising":
                pressure_signals += 1

        if supportive_signals == 2:
            return "MACRO_BULLISH"
        if pressure_signals == 2:
            return "MACRO_BEARISH"
        return "MIXED"

    def _calculate_readiness_score(self, data_completeness: int, regime: str) -> int:
        readiness_score = data_completeness
        if regime == "INSUFFICIENT_DATA":
            readiness_score = min(readiness_score, 55)
        return max(0, min(100, int(readiness_score)))

    def _build_no_trade_reasons(
        self,
        asset: str,
        regime: str,
        readiness_score: int,
        stale_sources: list[str],
        missing_sources: list[str],
    ) -> list[str]:
        reasons: list[str] = []
        if regime == "INSUFFICIENT_DATA":
            if asset == "BTC":
                reasons.append(
                    "BTC regime classification requires at least "
                    f"{self.config.min_snapshots_for_regime} persisted OK BTC price snapshots."
                )
            else:
                reasons.append(
                    "Gold regime classification requires at least "
                    f"{self.config.min_snapshots_for_regime} persisted OK US10Y and real-yield snapshots."
                )
        if stale_sources:
            reasons.append(f"Stale sources: {', '.join(stale_sources)}.")
        if missing_sources:
            reasons.append(f"Missing sources: {', '.join(missing_sources)}.")
        if readiness_score < self.config.min_readiness_score_for_decision:
            reasons.append(
                f"Readiness score {readiness_score} is below the configured minimum "
                f"{self.config.min_readiness_score_for_decision}."
            )
        return reasons

    def _timestamp_is_stale(self, row: dict[str, str], stale_key: str) -> bool:
        if str(row.get("status") or "") != "OK":
            return False

        threshold_minutes = self.config.stale_after_minutes.get(stale_key)
        if threshold_minutes is None:
            return False

        timestamp = self._parse_timestamp(row.get("timestamp"))
        if timestamp is None:
            return True

        age_minutes = (datetime.now(UTC) - timestamp).total_seconds() / 60
        return age_minutes > threshold_minutes

    @staticmethod
    def _range_pct(trend: MultiPointTrendResult) -> float:
        if trend.average_value in {None, 0} or trend.max_value is None or trend.min_value is None:
            return 0.0
        return abs((trend.max_value - trend.min_value) / trend.average_value) * 100

    def _trend_ready_for_regime(self, trend: MultiPointTrendResult | None) -> bool:
        return (
            trend is not None
            and trend.status == "OK"
            and trend.lookback_points >= self.config.min_snapshots_for_regime
        )

    @staticmethod
    def _parse_timestamp(raw_value: object) -> datetime | None:
        if raw_value in {None, ""}:
            return None
        text = str(raw_value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _connect_read_only(self) -> sqlite3.Connection:
        uri = f"{self.database_path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _fetch_latest_market_rows(connection: sqlite3.Connection) -> dict[tuple[str, str], dict[str, str]]:
        rows = connection.execute("SELECT * FROM market_snapshots ORDER BY id DESC").fetchall()
        latest_rows: dict[tuple[str, str], dict[str, str]] = {}
        for row in rows:
            key = (str(row["asset"]), str(row["data_type"]))
            if key not in latest_rows:
                latest_rows[key] = dict(row)
        return latest_rows

    def _disabled_result(self, asset: str) -> ResearchReadinessResult:
        return ResearchReadinessResult(
            asset=asset,
            readiness_score=0,
            regime="INSUFFICIENT_DATA",
            data_completeness=0,
            stale_sources=[],
            missing_sources=[],
            warnings=["Research readiness is disabled in config."],
            decision_ready=False,
            no_trade_reasons=["Research readiness is disabled in config."],
        )

    def _not_available_result(self, asset: str, message: str) -> ResearchReadinessResult:
        return ResearchReadinessResult(
            asset=asset,
            readiness_score=0,
            regime="INSUFFICIENT_DATA",
            data_completeness=0,
            stale_sources=[],
            missing_sources=[],
            warnings=[message],
            decision_ready=False,
            no_trade_reasons=[message],
        )

    def _failure_result(self, asset: str, message: str) -> ResearchReadinessResult:
        return ResearchReadinessResult(
            asset=asset,
            readiness_score=0,
            regime="INSUFFICIENT_DATA",
            data_completeness=0,
            stale_sources=[],
            missing_sources=[],
            warnings=[message],
            decision_ready=False,
            no_trade_reasons=[message],
        )
