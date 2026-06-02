from __future__ import annotations

from datetime import UTC, date, datetime

from core.models import (
    AnalysisResult,
    DailyBriefContext,
    DataQualityReport,
    HypothesisReviewSummary,
    MarketDataPoint,
    RiskStatus,
)
from reports.daily_report import DailyReportFormatter


def test_daily_report_includes_hypothesis_review_section() -> None:
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
            hypothesis_review_summary=HypothesisReviewSummary(
                total_outcomes=12,
                evaluated_outcomes=10,
                favorable_count=6,
                unfavorable_count=2,
                neutral_count=2,
                insufficient_followup_count=1,
                blocked_not_evaluated_count=1,
                favorable_rate=0.6,
                unfavorable_rate=0.2,
                neutral_rate=0.2,
                by_asset=[],
                by_strategy_family=[],
                by_regime=[],
                by_horizon=[],
                by_readiness_bucket=[],
                by_hypothesis_status=[],
                avg_move_pct=0.5,
                avg_max_favorable_move_pct=1.2,
                avg_max_adverse_move_pct=0.4,
                warnings=[],
                promoted_candidates=[{"strategy_family": "BTC_TREND_CONTINUATION", "asset": "BTC", "favorable_rate": 0.6, "evaluated_outcomes": 10}],
                blocked_candidates=[],
                created_at=datetime(2026, 6, 2, tzinfo=UTC),
                lookback_days=14,
            ),
        )
    )

    assert "Hypothesis Review Analytics:" in report
    assert "Evaluated: 10 | Favorable: 6 (60%)" in report
    assert "Review Candidate: BTC_TREND_CONTINUATION" in report


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
