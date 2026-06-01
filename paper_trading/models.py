from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PaperSignal:
    asset: str
    direction: str
    signal_source: str
    score: int
    bias: str
    confidence: str
    data_completeness: int
    intended_entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_pct: float = 0.0
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    active_profile: str = "conservative"
    review_reasons: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_trade_candidate(self) -> bool:
        return self.direction in {"LONG", "SHORT"}


@dataclass(frozen=True)
class PaperOrder:
    asset: str
    direction: str
    order_type: str
    status: str
    signal_source: str
    intended_entry: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_pct: float
    size: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    workflow_run_id: int | None = None
    id: int | None = None
    created_at: datetime | None = None
    rejection_reason: str | None = None


@dataclass(frozen=True)
class PaperPosition:
    asset: str
    direction: str
    entry_price: float
    size: float
    status: str
    stop_loss: float | None = None
    take_profit: float | None = None
    exit_price: float | None = None
    pnl_abs: float = 0.0
    pnl_pct: float = 0.0
    reasons: list[str] = field(default_factory=list)
    id: int | None = None
    order_id: int | None = None
    workflow_run_id: int | None = None
    opened_at: str | None = None
    closed_at: str | None = None


@dataclass(frozen=True)
class PaperTradeResult:
    status: str
    asset: str | None = None
    direction: str | None = None
    order_id: int | None = None
    position_id: int | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    size: float = 0.0
    pnl_abs: float = 0.0
    pnl_pct: float = 0.0
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PaperRiskState:
    approved: bool
    status: str
    reason_code: str
    reason: str
    equity: float
    daily_realized_pnl: float
    daily_loss_pct: float
    open_positions_count: int
    approved_size: float = 0.0
    risk_amount: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PaperSignalReview:
    workflow_run_id: int
    asset: str
    signal_action: str
    review_status: str
    bias: str
    total_score: int
    confidence: str
    data_completeness: int
    active_profile: str
    reasons: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    signal_source: str | None = None
    id: int | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class PaperJournalNote:
    note_type: str
    note_text: str
    reference_id: str | None = None
    asset: str | None = None
    profile: str | None = None
    title: str | None = None
    tags: str | None = None
    is_deleted: bool = False
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class PaperRunSummary:
    enabled: bool
    status: str
    workflow_run_id: int
    active_profile: str = "conservative"
    signals_evaluated: int = 0
    signals_accepted: int = 0
    signals_rejected: int = 0
    no_trade_count: int = 0
    orders_opened: int = 0
    positions_updated: int = 0
    equity_curve_id: int | None = None
    notes: list[str] = field(default_factory=list)
    run_summary_id: int | None = None

    def to_text(self) -> str:
        lines = [
            "Paper Trading Run",
            "SIMULATED ONLY - NO REAL EXECUTION",
            f"Status: {self.status}",
            f"Workflow Run ID: {self.workflow_run_id}",
            f"Active Profile: {self.active_profile}",
            f"Signals Evaluated: {self.signals_evaluated}",
            f"Signals Accepted: {self.signals_accepted}",
            f"Signals Rejected: {self.signals_rejected}",
            f"No-Trade Signals: {self.no_trade_count}",
            f"Simulated Orders Opened: {self.orders_opened}",
            f"Positions Updated: {self.positions_updated}",
        ]
        if self.equity_curve_id is not None:
            lines.append(f"Equity Snapshot ID: {self.equity_curve_id}")
        if self.notes:
            lines.append("Notes:")
            lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines)
