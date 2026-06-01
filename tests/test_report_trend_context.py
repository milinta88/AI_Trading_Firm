from __future__ import annotations

from datetime import UTC, date, datetime

from core.models import AnalysisResult, DailyBriefContext, DataQualityReport, MarketDataPoint, RiskStatus, TrendResult
from reports.daily_report import DailyReportFormatter


def test_report_includes_trend_context_sections() -> None:
    context = DailyBriefContext(
        run_date=date(2026, 5, 29),
        mode="research",
        macro_regime="Neutral",
        gold=AnalysisResult(asset="Gold", total_score=50, bias="Caution"),
        btc=AnalysisResult(asset="BTC", total_score=50, bias="Neutral"),
        market_data={
            "btc_price": _snapshot("btc_price", "BTC", "price", "OK", {"price": 100000.0}),
            "btc_fear_greed": _snapshot(
                "btc_fear_greed",
                "BTC",
                "fear_and_greed_index",
                "OK",
                {"value": 50, "classification": "Neutral"},
            ),
            "btc_funding_rate": _snapshot("btc_funding_rate", "BTC", "funding_rate", "OK", {"funding_rate": 0.0}),
            "btc_open_interest": _snapshot(
                "btc_open_interest",
                "BTC",
                "open_interest",
                "OK",
                {"open_interest": 1000.0},
            ),
            "gold_us10y": _snapshot("gold_us10y", "Gold", "us10y", "NOT_CONFIGURED", None),
            "gold_real_yield": _snapshot("gold_real_yield", "Gold", "real_yield", "NOT_CONFIGURED", None),
            "gold_fed_funds": _snapshot("gold_fed_funds", "Gold", "fed_funds", "NOT_CONFIGURED", None),
            "gold_cpi": _snapshot("gold_cpi", "Gold", "cpi", "NOT_CONFIGURED", None),
            "gold_dxy": _snapshot("gold_dxy", "Gold", "dxy", "NOT_CONFIGURED", None),
            "gold_spot_price": _snapshot("gold_spot_price", "Gold", "spot_price", "NOT_CONFIGURED", None),
        },
        data_quality=DataQualityReport("WARNING", {}, []),
        risk=RiskStatus("CAUTION", "WATCH ONLY", "WARNING", 0.0, 0.0, []),
        system_health={"SQLite": "OK"},
        trend_context={
            "btc_open_interest": TrendResult(
                "BTC",
                "open_interest",
                "OK",
                1200.0,
                1000.0,
                200.0,
                20.0,
                "rising",
                2,
                "BTC open interest is rising while price is rising, suggesting trend participation and leverage build-up.",
            ),
            "gold_us10y": TrendResult(
                "Gold",
                "us10y",
                "INSUFFICIENT_HISTORY",
                4.2,
                None,
                None,
                None,
                "unknown",
                1,
                "US10Y needs at least two persisted OK snapshots for trend analysis.",
            ),
        },
    )

    report_text = DailyReportFormatter().format(context)

    assert "BTC Trend Context:" in report_text
    assert "Open Interest: rising" in report_text
    assert "Gold Macro Trend Context:" in report_text
    assert "US10Y: INSUFFICIENT_HISTORY" in report_text


def _snapshot(
    key: str,
    asset: str,
    data_type: str,
    status: str,
    value: dict[str, object] | None,
) -> MarketDataPoint:
    return MarketDataPoint(key, asset, "test", data_type, status, datetime(2026, 5, 29, tzinfo=UTC), value)
