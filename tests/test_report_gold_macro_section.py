from __future__ import annotations

from datetime import UTC, date, datetime

from core.models import AnalysisResult, DailyBriefContext, DataQualityReport, MarketDataPoint, RiskStatus
from reports.daily_report import DailyReportFormatter
from scoring.models import ScoreComponent


def test_report_includes_available_gold_macro_values() -> None:
    formatter = DailyReportFormatter()
    context = DailyBriefContext(
        run_date=date(2026, 5, 28),
        mode="research",
        macro_regime="Neutral",
        gold=AnalysisResult(
            asset="Gold",
            total_score=65,
            bias="Bullish",
            confidence="Medium",
            data_completeness=67,
            components=[ScoreComponent("US10Y", "OK", {"latest_value": 4.2}, 10, 10, "Supportive.")],
            reasons=["US10Y and real yield are supportive."],
            warnings=["DXY is not configured yet."],
        ),
        btc=AnalysisResult(
            asset="BTC",
            total_score=62,
            bias="Bullish",
            confidence="Medium",
            data_completeness=100,
            components=[
                ScoreComponent("Funding Rate", "OK", {"funding_rate": 0.00038246}, -3, 10, "Crowded longs."),
                ScoreComponent("Open Interest", "OK", {"open_interest": 10659.509}, 0, 5, "Context only."),
            ],
            reasons=["Neutral."],
            warnings=[
                "Open interest is available but used as context only until trend history is added; "
                "confidence is capped at Medium."
            ],
        ),
        market_data={
            "btc_price": MarketDataPoint(
                key="btc_price",
                asset="BTC",
                source="Binance",
                data_type="price",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"price": 100000.0},
            ),
            "btc_fear_greed": MarketDataPoint(
                key="btc_fear_greed",
                asset="BTC",
                source="Alternative.me",
                data_type="fear_and_greed_index",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"value": 50, "classification": "Neutral"},
            ),
            "btc_funding_rate": MarketDataPoint(
                key="btc_funding_rate",
                asset="BTC",
                source="Binance USD-M Futures API",
                data_type="funding_rate",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"funding_rate": 0.00038246, "symbol": "BTCUSDT"},
            ),
            "btc_open_interest": MarketDataPoint(
                key="btc_open_interest",
                asset="BTC",
                source="Binance USD-M Futures API",
                data_type="open_interest",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"open_interest": 10659.509, "symbol": "BTCUSDT"},
            ),
            "gold_us10y": MarketDataPoint(
                key="gold_us10y",
                asset="Gold",
                source="FRED",
                data_type="us10y",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"latest_value": 4.2, "observation_date": "2026-05-28"},
            ),
            "gold_real_yield": MarketDataPoint(
                key="gold_real_yield",
                asset="Gold",
                source="FRED",
                data_type="real_yield",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"latest_value": 1.9, "observation_date": "2026-05-28"},
            ),
            "gold_fed_funds": MarketDataPoint(
                key="gold_fed_funds",
                asset="Gold",
                source="FRED",
                data_type="fed_funds",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"latest_value": 4.33, "observation_date": "2026-05-01"},
            ),
            "gold_cpi": MarketDataPoint(
                key="gold_cpi",
                asset="Gold",
                source="FRED",
                data_type="cpi",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"latest_value": 320.0, "observation_date": "2026-05-01"},
            ),
            "gold_dxy": MarketDataPoint(
                key="gold_dxy",
                asset="Gold",
                source="Macro Placeholder",
                data_type="dxy",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
            ),
            "gold_spot_price": MarketDataPoint(
                key="gold_spot_price",
                asset="Gold",
                source="Spot Gold Placeholder",
                data_type="spot_price",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
            ),
        },
        data_quality=DataQualityReport(
            overall_status="WARNING",
            source_statuses={"Gold Us10Y": "OK", "Gold Dxy": "NOT_CONFIGURED"},
            notes=["DXY is not configured yet."],
        ),
        risk=RiskStatus(
            status="CAUTION",
            trade_permission="WATCH ONLY",
            data_quality="WARNING",
            daily_loss_pct=0.0,
            weekly_loss_pct=0.0,
            notes=["Execution remains disabled."],
        ),
        system_health={"FRED": "WARNING", "Telegram": "DRY_RUN"},
    )

    report_text = formatter.format(context)

    assert "BTC Funding Rate: 0.0382%" in report_text
    assert "BTC Open Interest: 10,659.509" in report_text
    assert "US10Y: 4.2 (2026-05-28)" in report_text
    assert "Real Yield: 1.9 (2026-05-28)" in report_text
    assert "Fed Funds: 4.33 (2026-05-01)" in report_text
    assert "CPI: 320.0 (2026-05-01)" in report_text
