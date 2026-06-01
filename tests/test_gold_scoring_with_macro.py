from __future__ import annotations

from datetime import UTC, datetime

from core.models import MarketDataPoint
from scoring.gold_scoring import GoldScoringEngine


def test_gold_scoring_uses_falling_yields_as_supportive_signal() -> None:
    engine = GoldScoringEngine()

    result = engine.score(
        {
            "gold_dxy": _snapshot("gold_dxy", "dxy", "NOT_CONFIGURED"),
            "gold_us10y": _snapshot("gold_us10y", "us10y", "OK", latest_value=4.2, previous_value=4.4, change=-0.2),
            "gold_real_yield": _snapshot(
                "gold_real_yield",
                "real_yield",
                "OK",
                latest_value=1.9,
                previous_value=2.1,
                change=-0.2,
            ),
            "gold_fed_funds": _snapshot("gold_fed_funds", "fed_funds", "OK", latest_value=4.33),
            "gold_cpi": _snapshot("gold_cpi", "cpi", "OK", latest_value=320.0),
            "gold_spot_price": _snapshot("gold_spot_price", "spot_price", "NOT_CONFIGURED"),
        }
    )

    assert result.total_score == 75
    assert result.bias == "Bullish"
    assert result.confidence == "Medium"
    assert result.data_completeness == 67


def _snapshot(
    key: str,
    data_type: str,
    status: str,
    latest_value: float | None = None,
    previous_value: float | None = None,
    change: float | None = None,
) -> MarketDataPoint:
    direction = "unknown"
    if change is not None:
        if change > 0:
            direction = "rising"
        elif change < 0:
            direction = "falling"
        else:
            direction = "flat"

    return MarketDataPoint(
        key=key,
        asset="Gold",
        source="FRED",
        data_type=data_type,
        status=status,
        timestamp=datetime(2026, 5, 28, tzinfo=UTC),
        value=(
            {
                "latest_value": latest_value,
                "previous_value": previous_value,
                "change": change,
                "direction": direction,
                "observation_date": "2026-05-28",
            }
            if latest_value is not None
            else None
        ),
        error_summary=None if status == "OK" else "Not configured",
    )

