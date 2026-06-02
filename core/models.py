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
class HypothesisOutcome:
    hypothesis_id: int
    workflow_run_id: int
    asset: str
    hypothesis_name: str
    direction_bias: str
    strategy_family: str
    horizon_hours: int
    created_at: datetime
    evaluated_at: datetime
    entry_reference_price: float | None
    followup_price: float | None
    move_pct: float | None
    max_favorable_move_pct: float | None
    max_adverse_move_pct: float | None
    outcome_status: str
    reason: str
    warnings: list[str]


@dataclass(frozen=True)
class HypothesisReviewSummary:
    total_outcomes: int
    evaluated_outcomes: int
    favorable_count: int
    unfavorable_count: int
    neutral_count: int
    insufficient_followup_count: int
    blocked_not_evaluated_count: int
    favorable_rate: float
    unfavorable_rate: float
    neutral_rate: float
    by_asset: list[dict[str, Any]]
    by_strategy_family: list[dict[str, Any]]
    by_regime: list[dict[str, Any]]
    by_horizon: list[dict[str, Any]]
    by_readiness_bucket: list[dict[str, Any]]
    by_hypothesis_status: list[dict[str, Any]]
    avg_move_pct: float | None
    avg_max_favorable_move_pct: float | None
    avg_max_adverse_move_pct: float | None
    warnings: list[str]
    promoted_candidates: list[dict[str, Any]]
    blocked_candidates: list[dict[str, Any]]
    created_at: datetime | None = None
    lookback_days: int | None = None


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
    hypothesis_outcomes: list[HypothesisOutcome] = field(default_factory=list)
    hypothesis_review_summary: HypothesisReviewSummary | None = None


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
