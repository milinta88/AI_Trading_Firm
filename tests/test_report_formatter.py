from __future__ import annotations

from datetime import UTC, date, datetime

from core.models import AnalysisResult, DailyBriefContext, DataQualityReport, MarketDataPoint, RiskStatus
from reports.daily_report import DailyReportFormatter
from scoring.models import ScoreComponent


def test_daily_report_formatter_includes_key_sections() -> None:
    formatter = DailyReportFormatter()
    brief = DailyBriefContext(
        run_date=date(2026, 5, 28),
        mode="research",
        macro_regime="Neutral",
        gold=AnalysisResult(
            asset="Gold",
            total_score=50,
            bias="Neutral",
            confidence="Low",
            data_completeness=0,
            components=[
                ScoreComponent(
                    name="DXY",
                    status="NOT_CONFIGURED",
                    raw_value=None,
                    score_contribution=0,
                    max_score=15,
                    reason="DXY live macro data is not configured yet.",
                )
            ],
            reasons=["Reason one", "Reason two"],
            warnings=["Gold live macro data is not configured yet."],
        ),
        btc=AnalysisResult(
            asset="BTC",
            total_score=62,
            bias="Bullish",
            confidence="Medium",
            data_completeness=100,
            components=[
                ScoreComponent(
                    name="Fear & Greed",
                    status="OK",
                    raw_value=62,
                    score_contribution=10,
                    max_score=15,
                    reason="Constructive sentiment.",
                ),
                ScoreComponent(
                    name="Funding Rate",
                    status="OK",
                    raw_value={"funding_rate": 0.00038246},
                    score_contribution=-3,
                    max_score=10,
                    reason="Funding rate is modestly positive.",
                ),
                ScoreComponent(
                    name="Open Interest",
                    status="OK",
                    raw_value={"open_interest": 10659.509},
                    score_contribution=0,
                    max_score=5,
                    reason="Open interest is contextual.",
                ),
            ],
            reasons=["Reason A", "Reason B"],
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
                timestamp=datetime(2026, 5, 28, 0, 0, tzinfo=UTC),
                value={"price": 108000.12, "symbol": "BTCUSDT"},
            ),
            "btc_fear_greed": MarketDataPoint(
                key="btc_fear_greed",
                asset="BTC",
                source="Alternative.me",
                data_type="fear_and_greed_index",
                status="OK",
                timestamp=datetime(2026, 5, 28, 0, 0, tzinfo=UTC),
                value={"value": 62, "classification": "Greed"},
            ),
            "btc_funding_rate": MarketDataPoint(
                key="btc_funding_rate",
                asset="BTC",
                source="Binance USD-M Futures API",
                data_type="funding_rate",
                status="OK",
                timestamp=datetime(2026, 5, 28, 0, 0, tzinfo=UTC),
                value={"funding_rate": 0.00038246, "symbol": "BTCUSDT"},
            ),
            "btc_open_interest": MarketDataPoint(
                key="btc_open_interest",
                asset="BTC",
                source="Binance USD-M Futures API",
                data_type="open_interest",
                status="OK",
                timestamp=datetime(2026, 5, 28, 0, 0, tzinfo=UTC),
                value={"open_interest": 10659.509, "symbol": "BTCUSDT"},
            ),
            "gold_dxy": MarketDataPoint(
                key="gold_dxy",
                asset="Gold",
                source="FRED Placeholder",
                data_type="dxy",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, 0, 0, tzinfo=UTC),
            ),
            "gold_us10y": MarketDataPoint(
                key="gold_us10y",
                asset="Gold",
                source="FRED Placeholder",
                data_type="us10y",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, 0, 0, tzinfo=UTC),
            ),
            "gold_real_yield": MarketDataPoint(
                key="gold_real_yield",
                asset="Gold",
                source="FRED Placeholder",
                data_type="real_yield",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, 0, 0, tzinfo=UTC),
            ),
            "gold_fed_funds": MarketDataPoint(
                key="gold_fed_funds",
                asset="Gold",
                source="FRED",
                data_type="fed_funds",
                status="OK",
                timestamp=datetime(2026, 5, 28, 0, 0, tzinfo=UTC),
                value={"latest_value": 4.33, "observation_date": "2026-05-01"},
            ),
            "gold_cpi": MarketDataPoint(
                key="gold_cpi",
                asset="Gold",
                source="FRED",
                data_type="cpi",
                status="OK",
                timestamp=datetime(2026, 5, 28, 0, 0, tzinfo=UTC),
                value={"latest_value": 320.0, "observation_date": "2026-05-01"},
            ),
            "gold_spot_price": MarketDataPoint(
                key="gold_spot_price",
                asset="Gold",
                source="Spot Gold Placeholder",
                data_type="spot_price",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, 0, 0, tzinfo=UTC),
            ),
        },
        data_quality=DataQualityReport(
            overall_status="WARNING",
            source_statuses={
                "BTC Price": "OK",
                "BTC Fear And Greed Index": "OK",
                "BTC Funding Rate": "OK",
                "BTC Open Interest": "OK",
                "Gold Dxy": "NOT_CONFIGURED",
            },
            notes=["Gold DXY is not configured yet."],
        ),
        risk=RiskStatus(
            status="NORMAL",
            trade_permission="WATCH ONLY",
            data_quality="WARNING",
            daily_loss_pct=0.0,
            weekly_loss_pct=0.0,
            notes=["Research only", "Execution disabled"],
        ),
        system_health={
            "SQLite": "OK",
            "Telegram": "DRY_RUN",
            "BTC public data": "OK",
            "BTC derivatives data": "OK",
        },
    )

    report_text = formatter.format(brief)

    assert "AI Trading Firm Daily Brief" in report_text
    assert "Execution: Disabled (MVP Phase 1)" in report_text
    assert "Market Data:" in report_text
    assert "BTC Price: 108,000.12 USDT" in report_text
    assert "Fear & Greed Index: 62 (Greed)" in report_text
    assert "BTC Funding Rate: 0.0382%" in report_text
    assert "BTC Open Interest: 10,659.509" in report_text
    assert "Fed Funds: 4.33 (2026-05-01)" in report_text
    assert "CPI: 320.0 (2026-05-01)" in report_text
    assert "Total Score: 62/100" in report_text
    assert "Confidence: Medium" in report_text
    assert "Data Completeness: 100%" in report_text
    assert "confidence is capped at Medium" in report_text
    assert "Score Breakdown:" in report_text
    assert "Data Quality:" in report_text
    assert "Gold:" in report_text
    assert "BTC:" in report_text
    assert "Risk Status:" in report_text
    assert "System Health:" in report_text
    assert "BTC derivatives data: OK" in report_text
    assert "Telegram: DRY_RUN" in report_text
