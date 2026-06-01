from __future__ import annotations

from datetime import date

from core.config import PaperTradingConfig
from paper_trading.models import PaperRiskState, PaperSignal
from paper_trading.repository import PaperTradingRepository


class PaperRiskEngine:
    """Risk checks for simulated paper orders only."""

    def __init__(self, config: PaperTradingConfig, repository: PaperTradingRepository) -> None:
        self.config = config
        self.repository = repository

    def evaluate(
        self,
        signal: PaperSignal,
        workflow_run_id: int | None,
        run_date: date,
        data_quality_status: str,
    ) -> PaperRiskState:
        equity = self.repository.latest_equity(self.config.starting_equity)
        daily_realized_pnl = self.repository.realized_pnl_for_date(run_date)
        daily_loss_pct = self._daily_loss_pct(equity, daily_realized_pnl)
        open_positions_count = self.repository.count_open_positions()

        rejection = self._first_rejection(signal, data_quality_status, equity, daily_loss_pct, open_positions_count)
        if rejection:
            reason_code, reason = rejection
            state = PaperRiskState(
                approved=False,
                status="REJECTED" if signal.is_trade_candidate else "SKIPPED",
                reason_code=reason_code,
                reason=reason,
                equity=equity,
                daily_realized_pnl=daily_realized_pnl,
                daily_loss_pct=daily_loss_pct,
                open_positions_count=open_positions_count,
                warnings=signal.warnings,
            )
            self._store_event(workflow_run_id, signal, state)
            return state

        stop_distance = abs(float(signal.intended_entry) - float(signal.stop_loss))
        risk_amount = equity * (signal.risk_pct / 100)
        approved_size = risk_amount / stop_distance if stop_distance else 0.0
        state = PaperRiskState(
            approved=True,
            status="APPROVED",
            reason_code="SIGNAL_ACCEPTED",
            reason="Paper signal passed simulated risk checks.",
            equity=equity,
            daily_realized_pnl=daily_realized_pnl,
            daily_loss_pct=daily_loss_pct,
            open_positions_count=open_positions_count,
            approved_size=approved_size,
            risk_amount=risk_amount,
            warnings=signal.warnings,
        )
        self._store_event(workflow_run_id, signal, state)
        return state

    def _first_rejection(
        self,
        signal: PaperSignal,
        data_quality_status: str,
        equity: float,
        daily_loss_pct: float,
        open_positions_count: int,
    ) -> tuple[str, str] | None:
        if not self.config.enabled:
            return "RISK_REJECTED", "Paper trading is disabled in config."

        if not signal.is_trade_candidate:
            return "NO_TRADE", "Paper signal is NO_TRADE; no simulated order will be created."

        if data_quality_status == "FAIL":
            return "DATA_QUALITY_NOT_ACCEPTABLE", "Data quality is FAIL; simulated order rejected."

        if signal.direction == "LONG" and not self.config.allow_long:
            return "RISK_REJECTED", "Long paper signals are disabled by config."

        if signal.direction == "SHORT" and not self.config.allow_short:
            return "RISK_REJECTED", "Short paper signals are disabled by config."

        if open_positions_count >= self.config.max_open_positions:
            return "RISK_REJECTED", "Maximum open simulated positions reached."

        if signal.risk_pct > self.config.max_risk_per_trade_pct:
            return "RISK_REJECTED", "Signal risk exceeds max_risk_per_trade_pct."

        if daily_loss_pct >= self.config.max_daily_loss_pct:
            return "RISK_REJECTED", "Maximum simulated daily loss threshold reached."

        if equity <= 0:
            return "RISK_REJECTED", "Paper equity is not positive."

        if signal.intended_entry is None or signal.stop_loss is None:
            return "RISK_REJECTED", "Signal is missing intended entry or stop loss."

        if abs(signal.intended_entry - signal.stop_loss) <= 0:
            return "RISK_REJECTED", "Signal stop distance is zero."

        return None

    def _store_event(self, workflow_run_id: int | None, signal: PaperSignal, state: PaperRiskState) -> None:
        self.repository.store_risk_event(
            workflow_run_id=workflow_run_id,
            asset=signal.asset,
            event_type="PAPER_SIGNAL_RISK_CHECK",
            status=state.status,
            reason=state.reason,
            details={
                "signal_source": signal.signal_source,
                "direction": signal.direction,
                "score": signal.score,
                "bias": signal.bias,
                "confidence": signal.confidence,
                "data_completeness": signal.data_completeness,
                "is_trade_candidate": signal.is_trade_candidate,
                "review_category": "NO_TRADE" if state.status == "SKIPPED" else state.status,
                "active_profile": signal.active_profile,
                "reason_code": state.reason_code,
                "risk_pct": signal.risk_pct,
                "approved_size": state.approved_size,
                "simulated_only": True,
            },
        )

    @staticmethod
    def _daily_loss_pct(equity: float, daily_realized_pnl: float) -> float:
        if equity <= 0 or daily_realized_pnl >= 0:
            return 0.0
        return abs(daily_realized_pnl) / equity * 100
