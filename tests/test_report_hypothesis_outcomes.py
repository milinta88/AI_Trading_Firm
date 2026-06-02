from __future__ import annotations

from datetime import UTC, date, datetime

from core.models import (
    AnalysisResult,
    DailyBriefContext,
    DataQualityReport,
    HypothesisOutcome,
    MarketDataPoint,
    RiskStatus,
)
from reports.daily_report import DailyReportFormatter


def test_daily_report_includes_hypothesis_outcomes_section() -> None:
    report = DailyReportFormatter().format(
        DailyBriefContext(
            run_date=date(2026, 6, 2),
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
            hypothesis_outcomes=[
                HypothesisOutcome(
                    hypothesis_id=1,
                    workflow_run_id=1,
                    asset="BTC",
                    hypothesis_name="BTC Trend Continuation Research Hypothesis",
                    direction_bias="LONG",
                    strategy_family="BTC_TREND_CONTINUATION",
                    horizon_hours=24,
                    created_at=datetime(2026, 6, 1, tzinfo=UTC),
                    evaluated_at=datetime(2026, 6, 2, tzinfo=UTC),
                    entry_reference_price=100.0,
                    followup_price=101.0,
                    move_pct=1.0,
                    max_favorable_move_pct=1.5,
                    max_adverse_move_pct=0.3,
                    outcome_status="FAVORABLE",
                    reason="LONG hypothesis moved favorably.",
                    warnings=[],
                )
            ],
        )
    )

    assert "Hypothesis Outcomes:" in report
    assert "BTC 24h: FAVORABLE" in report


def _market_data() -> dict[str, MarketDataPoint]:
    timestamp = datetime(2026, 6, 2, tzinfo=UTC)
    return {
        "btc_price": MarketDataPoint("btc_price", "BTC", "test", "price", "OK", timestamp, {"price": 100000.0}),
        "btc_fear_greed": MarketDataPoint("btc_fear_greed", "BTC", "test", "fear_and_greed_index", "OK", timestamp, {"value": 50, "classification": "Neutral"}),
        "btc_funding_rate": MarketDataPoint("btc_funding_rate", "BTC", "test", "funding_rate", "OK", timestamp, {"funding_rate": 0.0001}),
        "btc_open_interest": MarketDataPoint("btc_open_interest", "BTC", "test", "open_interest", "OK", timestamp, {"open_interest": 1000.0}),
        "gold_us10y": MarketDataPoint("gold_us10y", "Gold", "test", "us10y", "OK", timestamp, {"latest_value": 4.3, "observation_date": "2026-06-01"}),
        "gold_real_yield": MarketDataPoint("gold_real_yield", "Gold", "test", "real_yield", "OK", timestamp, {"latest_value": 2.0, "observation_date": "2026-06-01"}),
        "gold_fed_funds": MarketDataPoint("gold_fed_funds", "Gold", "test", "fed_funds", "OK", timestamp, {"latest_value": 4.0, "observation_date": "2026-06-01"}),
        "gold_cpi": MarketDataPoint("gold_cpi", "Gold", "test", "cpi", "OK", timestamp, {"latest_value": 320.0, "observation_date": "2026-06-01"}),
        "gold_dxy": MarketDataPoint("gold_dxy", "Gold", "test", "dxy", "OK", timestamp, {"latest_value": 101.0, "quote_timestamp": "2026-06-02"}),
        "gold_spot_price": MarketDataPoint("gold_spot_price", "Gold", "test", "spot_price", "OK", timestamp, {"latest_value": 2400.0, "quote_timestamp": "2026-06-02"}),
    }
