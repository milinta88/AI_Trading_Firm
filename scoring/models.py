from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    status: str
    raw_value: Any
    score_contribution: int
    max_score: int
    reason: str


@dataclass(frozen=True)
class ScoreResult:
    asset: str
    total_score: int
    bias: str
    confidence: str = "Low"
    data_completeness: int = 0
    components: list[ScoreComponent] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        return self.total_score

