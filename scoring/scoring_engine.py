from __future__ import annotations

from scoring.models import ScoreComponent


class RuleBasedScoringEngine:
    """Shared helpers for deterministic research-only scoring."""

    _CONFIDENCE_ORDER = {
        "Low": 0,
        "Medium": 1,
        "High": 2,
    }

    @staticmethod
    def clamp_score(score: int) -> int:
        return max(0, min(100, int(score)))

    @staticmethod
    def calculate_data_completeness(components: list[ScoreComponent]) -> int:
        if not components:
            return 0

        ok_count = sum(1 for component in components if component.status == "OK")
        return int(round((ok_count / len(components)) * 100))

    def derive_confidence(self, data_completeness: int, max_confidence: str = "High") -> str:
        if data_completeness < 40:
            derived = "Low"
        elif data_completeness <= 75:
            derived = "Medium"
        else:
            derived = "High"

        if self._CONFIDENCE_ORDER[derived] > self._CONFIDENCE_ORDER[max_confidence]:
            return max_confidence
        return derived

