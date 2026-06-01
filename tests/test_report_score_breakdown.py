from __future__ import annotations

from datetime import UTC, date, datetime

from core.models import AnalysisResult, DailyBriefContext, DataQualityReport, MarketDataPoint, RiskStatus
from reports.daily_report import DailyReportFormatter
from scoring.models import ScoreComponent


def test_daily_report_includes_score_breakdown_sections() -> None:
    formatter = DailyReportFormatter()

    context = DailyBriefContext(
        run_date=date(2026, 5, 28),
        mode="research",
        macro_regime="Neutral",
        gold=AnalysisResult(
            asset="Gold",
            total_score=50,
            bias="Neutral",
            confidence="Low",
            data_completeness=0,
            components=[ScoreComponent("DXY", "NOT_CONFIGURED", None, 0, 15, "Not configured.")],
            reasons=["Gold remains placeholder-based."],
            warnings=["Gold macro live data is not configured."],
        ),
        btc=AnalysisResult(
            asset="BTC",
            total_score=62,
            bias="Bullish",
            confidence="Medium",
            data_completeness=100,
            components=[
                ScoreComponent("Fear & Greed", "OK", 65, 10, 15, "Constructive."),
                ScoreComponent("Funding Rate", "OK", {"funding_rate": 0.00038246}, -3, 10, "Crowded longs."),
                ScoreComponent("Open Interest", "OK", {"open_interest": 10659.509}, 0, 5, "Context only."),
            ],
            reasons=["BTC sentiment is constructive."],
            warnings=[
                "Open interest is available but used as context only until trend history is added; "
                "confidence is capped at Medium."
            ],
        ),
        market_data={
            "btc_price": MarketDataPoint(
                key="btc_price",
                asset="BTC",
                source="Binance Spot API",
                data_type="price",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"price": 100000.0, "symbol": "BTCUSDT"},
            ),
            "btc_fear_greed": MarketDataPoint(
                key="btc_fear_greed",
                asset="BTC",
                source="Alternative.me",
                data_type="fear_and_greed_index",
                status="OK",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
                value={"value": 65, "classification": "Greed"},
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
            "gold_dxy": MarketDataPoint(
                key="gold_dxy",
                asset="Gold",
                source="FRED Placeholder",
                data_type="dxy",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
            ),
            "gold_us10y": MarketDataPoint(
                key="gold_us10y",
                asset="Gold",
                source="FRED Placeholder",
                data_type="us10y",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
            ),
            "gold_real_yield": MarketDataPoint(
                key="gold_real_yield",
                asset="Gold",
                source="FRED Placeholder",
                data_type="real_yield",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
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
            source_statuses={"BTC Price": "OK", "Gold Dxy": "NOT_CONFIGURED"},
            notes=["Gold DXY is not configured yet."],
        ),
        risk=RiskStatus(
            status="CAUTION",
            trade_permission="WATCH ONLY",
            data_quality="WARNING",
            daily_loss_pct=0.0,
            weekly_loss_pct=0.0,
            notes=["Low confidence detected for: Gold."],
        ),
        system_health={"SQLite": "OK", "Telegram": "DRY_RUN"},
    )

    report_text = formatter.format(context)

    assert "Score Breakdown:" in report_text
    assert "- Fear & Greed: +10/15 (OK)" in report_text
    assert "- Funding Rate: -3/10 (OK) value=0.0382%" in report_text
    assert "- Open Interest: +0/5 (OK) value=10,659.509" in report_text
    assert "Warnings:" in report_text
    assert "confidence is capped at Medium" in report_text
    assert "Data Completeness: 100%" in report_text
