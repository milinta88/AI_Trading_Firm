from __future__ import annotations

from agents.risk_officer_bot import RiskOfficerBot
from core.models import AnalysisResult
from scoring.models import ScoreComponent


def test_risk_officer_returns_normal_for_constructive_placeholder_scores() -> None:
    bot = RiskOfficerBot(max_daily_loss_pct=1.0, max_weekly_loss_pct=3.0, execution_enabled=False)

    result = bot.evaluate(
        gold_result=AnalysisResult(
            asset="Gold",
            total_score=72,
            bias="Bullish",
            confidence="High",
            data_completeness=100,
            components=[ScoreComponent("DXY", "OK", 1.0, 5, 5, "Ready")],
            reasons=["x"],
        ),
        btc_result=AnalysisResult(
            asset="BTC",
            total_score=68,
            bias="Bullish",
            confidence="High",
            data_completeness=100,
            components=[ScoreComponent("Price", "OK", 1.0, 5, 5, "Ready")],
            reasons=["y"],
        ),
    )

    assert result.status == "NORMAL"
    assert result.trade_permission == "WATCH ONLY"
    assert result.data_quality == "PASS"


def test_risk_officer_returns_elevated_when_any_asset_score_is_weak() -> None:
    bot = RiskOfficerBot(max_daily_loss_pct=1.0, max_weekly_loss_pct=3.0, execution_enabled=False)

    result = bot.evaluate(
        gold_result=AnalysisResult(
            asset="Gold",
            total_score=49,
            bias="Bearish",
            confidence="Low",
            data_completeness=0,
            components=[],
            reasons=["x"],
        ),
        btc_result=AnalysisResult(
            asset="BTC",
            total_score=68,
            bias="Bullish",
            confidence="Medium",
            data_completeness=50,
            components=[],
            reasons=["y"],
        ),
    )

    assert result.status == "ELEVATED"
    assert any("below the research threshold" in note for note in result.notes)
