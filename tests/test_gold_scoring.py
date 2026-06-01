from __future__ import annotations

from datetime import UTC, datetime

from core.models import MarketDataPoint
from scoring.gold_scoring import GoldScoringEngine


def test_gold_scoring_stays_neutral_with_placeholder_macro_inputs() -> None:
    engine = GoldScoringEngine()

    result = engine.score(
        {
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
            "gold_spot_price": MarketDataPoint(
                key="gold_spot_price",
                asset="Gold",
                source="Spot Gold Placeholder",
                data_type="spot_price",
                status="NOT_CONFIGURED",
                timestamp=datetime(2026, 5, 28, tzinfo=UTC),
            ),
        }
    )

    assert result.total_score == 50
    assert result.bias == "Caution"
    assert result.confidence == "Low"
    assert result.data_completeness == 0
    assert any("not configured" in warning.lower() for warning in result.warnings)
