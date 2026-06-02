from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from scoring.models import ScoreResult


AnalysisResult = ScoreResult


@dataclass(frozen=True)
class RiskStatus:
    status: str
    trade_permission: str
    data_quality: str
    daily_loss_pct: float
    weekly_loss_pct: float
    notes: list[str]


@dataclass(frozen=True)
class TrendResult:
    asset: str
    data_type: str
    status: str
    latest_value: float | None
    previous_value: float | None
    change_abs: float | None
    change_pct: float | None
    direction: str
    lookback_points: int
    reason: str


@dataclass(frozen=True)
class MultiPointTrendResult:
    asset: str
    data_type: str
    status: str
    latest_value: float | None
    first_value: float | None
    average_value: float | None
    min_value: float | None
    max_value: float | None
    change_abs: float | None
    change_pct: float | None
    direction: str
    trend_strength: str
    lookback_points: int
    reason: str


@dataclass(frozen=True)
class ResearchReadinessResult:
    asset: str
    readiness_score: int
    regime: str
    data_completeness: int
    stale_sources: list[str]
    missing_sources: list[str]
    warnings: list[str]
    decision_ready: bool
    no_trade_reasons: list[str]


@dataclass(frozen=True)
class StrategyHypothesis:
    asset: str
    hypothesis_name: str
    direction_bias: str
    regime: str
    readiness_score: int
    score: int
    confidence: str
    data_completeness: int
    hypothesis_status: str
    reasons: list[str]
    blockers: list[str]
    warnings: list[str]
    suggested_strategy_family: str
    suggested_holding_period: str
    invalidation_notes: str
    created_at: datetime


@dataclass(frozen=True)
class DailyBriefContext:
    run_date: date
    mode: str
    macro_regime: str
    gold: AnalysisResult
    btc: AnalysisResult
    market_data: dict[str, "MarketDataPoint"]
    data_quality: "DataQualityReport"
    risk: RiskStatus
    system_health: dict[str, str]
    trend_context: dict[str, TrendResult] = field(default_factory=dict)
    research_readiness: dict[str, ResearchReadinessResult] = field(default_factory=dict)
    strategy_hypotheses: dict[str, StrategyHypothesis] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketDataPoint:
    key: str
    asset: str
    source: str
    data_type: str
    status: str
    timestamp: datetime
    value: dict[str, Any] | None = None
    error_summary: str | None = None


@dataclass(frozen=True)
class DataQualityReport:
    overall_status: str
    source_statuses: dict[str, str]
    notes: list[str]


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    status: str
    recipient: str
    detail: str | None = None
    message_id: int | None = None


@dataclass(frozen=True)
class WorkflowOutcome:
    workflow_run_id: int
    report_text: str
    delivery: DeliveryResult
