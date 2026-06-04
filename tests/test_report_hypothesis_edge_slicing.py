from __future__ import annotations

from datetime import UTC, date, datetime

from core.models import (
    AnalysisResult,
    DailyBriefContext,
    DataQualityReport,
    HypothesisEdgeSliceRow,
    HypothesisEdgeSliceSummary,
    MarketDataPoint,
    RiskStatus,
)
from reports.daily_report import DailyReportFormatter


def test_daily_report_includes_hypothesis_edge_slicing_section() -> None:
    row = HypothesisEdgeSliceRow(
        slice_key="BTC|BTC_TREND_CONTINUATION|TREND_UP|24|HIGH|HIGH|MONDAY",
        asset="BTC",
        strategy_family="BTC_TREND_CONTINUATION",
        regime="TREND_UP",
        horizon_hours=24,
        readiness_bucket="HIGH",
        confidence_bucket="HIGH",
        weekday="MONDAY",
        sample_size=10,
        favorable_count=7,
        unfavorable_count=1,
        neutral_count=2,
        favorable_rate=0.7,
        unfavorable_rate=0.1,
        neutral_rate=0.2,
        avg_move_pct=0.9,
        avg_max_favorable_move_pct=1.4,
        avg_max_adverse_move_pct=0.4,
        stability_status="STRONG_POSITIVE",
        candidate_status="REVIEW_CANDIDATE",
        warnings=[],
    )
    report = DailyReportFormatter().format(
        DailyBriefContext(
            run_date=date(2026, 6, 4),
            mode="research",
            macro_regime="Neutral",
            gold=AnalysisResult(asset="Gold", total_score=50, bias="Neutral", confidence="Medium", data_completeness=100),
            btc=AnalysisResult(asset="BTC", total_score=66, bias="Bullish", confidence="High", data_completeness=100),
            market_data=_market_data(),
            data_quality=DataQualityReport(overall_status="PASS", source_statuses={}, notes=[]),
            risk=RiskStatus(
                status="CAUTION",
                trade_permission="WATCH ONLY",
                data_quality="PASS",
                daily_loss_pct=0.0,
                weekly_loss_pct=0.0,
                notes=["Execution disabled."],
            ),
            system_health={"SQLite": "OK"},
            hypothesis_edge_slice_summary=HypothesisEdgeSliceSummary(
                total_slices=3,
                generated_at=datetime(2026, 6, 4, tzinfo=UTC),
                lookback_days=90,
                slice_rows=[row],
                warnings=["2 slices remain below the minimum sample size of 10."],
                strongest_slices=[row],
                weakest_slices=[],
                unstable_slices=[],
            ),
        )
    )

    assert "Hypothesis Edge Slicing:" in report
    assert "Total Slices: 3 | Strongest: 1" in report
    assert "Strongest: BTC BTC_TREND_CONTINUATION TREND_UP 24h STRONG_POSITIVE" in report


def _market_data() -> dict[str, MarketDataPoint]:
    timestamp = datetime(2026, 6, 4, tzinfo=UTC)
    return {
        "btc_price": MarketDataPoint("btc_price", "BTC", "test", "price", "OK", timestamp, {"price": 100000.0}),
        "btc_fear_greed": MarketDataPoint("btc_fear_greed", "BTC", "test", "fear_and_greed_index", "OK", timestamp, {"value": 50, "classification": "Neutral"}),
        "btc_funding_rate": MarketDataPoint("btc_funding_rate", "BTC", "test", "funding_rate", "OK", timestamp, {"funding_rate": 0.0001}),
        "btc_open_interest": MarketDataPoint("btc_open_interest", "BTC", "test", "open_interest", "OK", timestamp, {"open_interest": 1000.0}),
        "gold_us10y": MarketDataPoint("gold_us10y", "Gold", "test", "us10y", "OK", timestamp, {"latest_value": 4.3, "observation_date": "2026-06-01"}),
        "gold_real_yield": MarketDataPoint("gold_real_yield", "Gold", "test", "real_yield", "OK", timestamp, {"latest_value": 2.0, "observation_date": "2026-06-01"}),
        "gold_fed_funds": MarketDataPoint("gold_fed_funds", "Gold", "test", "fed_funds", "OK", timestamp, {"latest_value": 4.0, "observation_date": "2026-06-01"}),
        "gold_cpi": MarketDataPoint("gold_cpi", "Gold", "test", "cpi", "OK", timestamp, {"latest_value": 320.0, "observation_date": "2026-06-01"}),
        "gold_dxy": MarketDataPoint("gold_dxy", "Gold", "test", "dxy", "OK", timestamp, {"latest_value": 101.0, "quote_timestamp": "2026-06-04"}),
        "gold_spot_price": MarketDataPoint("gold_spot_price", "Gold", "test", "spot_price", "OK", timestamp, {"latest_value": 2400.0, "quote_timestamp": "2026-06-04"}),
    }
