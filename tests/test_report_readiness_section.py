from __future__ import annotations

from datetime import UTC, date, datetime

from core.models import (
    AnalysisResult,
    DailyBriefContext,
    DataQualityReport,
    MarketDataPoint,
    ResearchReadinessResult,
    RiskStatus,
)
from reports.daily_report import DailyReportFormatter


def test_daily_report_includes_market_regime_and_data_readiness_section() -> None:
    context = DailyBriefContext(
        run_date=date(2026, 6, 1),
        mode="research",
        macro_regime="Neutral",
        gold=AnalysisResult(
            asset="Gold",
            total_score=50,
            bias="Neutral",
            confidence="Low",
            data_completeness=20,
            components=[],
            reasons=["Gold research is incomplete."],
            warnings=["Gold macro stack is partial."],
        ),
        btc=AnalysisResult(
            asset="BTC",
            total_score=60,
            bias="Neutral",
            confidence="Medium",
            data_completeness=100,
            components=[],
            reasons=["BTC research is available."],
            warnings=[],
        ),
        market_data={
            "btc_price": MarketDataPoint(
                key="btc_price",
                asset="BTC",
                source="test",
                data_type="price",
                status="OK",
                timestamp=datetime(2026, 6, 1, tzinfo=UTC),
                value={"price": 100000.0},
            ),
            "btc_fear_greed": MarketDataPoint(
                key="btc_fear_greed",
                asset="BTC",
                source="test",
                data_type="fear_and_greed_index",
                status="OK",
                timestamp=datetime(2026, 6, 1, tzinfo=UTC),
                value={"value": 50, "classification": "Neutral"},
            ),
            "btc_funding_rate": MarketDataPoint(
                key="btc_funding_rate",
                asset="BTC",
                source="test",
                data_type="funding_rate",
                status="OK",
                timestamp=datetime(2026, 6, 1, tzinfo=UTC),
                value={"funding_rate": 0.0001},
            ),
            "btc_open_interest": MarketDataPoint(
                key="btc_open_interest",
                asset="BTC",
                source="test",
                data_type="open_interest",
                status="OK",
                timestamp=datetime(2026, 6, 1, tzinfo=UTC),
                value={"open_interest": 1000.0},
            ),
            "gold_us10y": MarketDataPoint(
                key="gold_us10y",
                asset="Gold",
                source="test",
                data_type="us10y",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            "gold_real_yield": MarketDataPoint(
                key="gold_real_yield",
                asset="Gold",
                source="test",
                data_type="real_yield",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            "gold_fed_funds": MarketDataPoint(
                key="gold_fed_funds",
                asset="Gold",
                source="test",
                data_type="fed_funds",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            "gold_cpi": MarketDataPoint(
                key="gold_cpi",
                asset="Gold",
                source="test",
                data_type="cpi",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            "gold_dxy": MarketDataPoint(
                key="gold_dxy",
                asset="Gold",
                source="test",
                data_type="dxy",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            "gold_spot_price": MarketDataPoint(
                key="gold_spot_price",
                asset="Gold",
                source="test",
                data_type="spot_price",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 6, 1, tzinfo=UTC),
            ),
        },
        data_quality=DataQualityReport(overall_status="WARNING", source_statuses={}, notes=[]),
        risk=RiskStatus(
            status="ELEVATED",
            trade_permission="WATCH ONLY",
            data_quality="WARNING",
            daily_loss_pct=0.0,
            weekly_loss_pct=0.0,
            notes=["Execution disabled."],
        ),
        system_health={"SQLite": "OK"},
        research_readiness={
            "BTC": ResearchReadinessResult(
                asset="BTC",
                readiness_score=82,
                regime="TREND_UP",
                data_completeness=100,
                stale_sources=[],
                missing_sources=[],
                warnings=[],
                decision_ready=True,
                no_trade_reasons=[],
            ),
            "Gold": ResearchReadinessResult(
                asset="Gold",
                readiness_score=20,
                regime="INSUFFICIENT_DATA",
                data_completeness=20,
                stale_sources=[],
                missing_sources=["Gold DXY", "Gold Spot Price"],
                warnings=["Gold macro data is partial."],
                decision_ready=False,
                no_trade_reasons=["Missing sources: Gold DXY, Gold Spot Price."],
            ),
        },
    )

    report_text = DailyReportFormatter().format(context)

    assert "Market Regime And Data Readiness:" in report_text
    assert "BTC:" in report_text
    assert "Regime: TREND_UP | Readiness Score: 82/100 | Decision Ready: YES" in report_text
    assert "Gold:" in report_text
    assert "Missing sources: Gold DXY, Gold Spot Price." in report_text

