from __future__ import annotations

from core.config import PaperTradingConfig
from paper_trading.models import PaperOrder, PaperPosition, PaperRiskState, PaperSignal, PaperTradeResult
from paper_trading.repository import PaperTradingRepository, unrealized_pnl_for_position


class PaperExecutionSimulator:
    """Simulates order fills and position lifecycle locally in SQLite only."""

    def __init__(self, config: PaperTradingConfig, repository: PaperTradingRepository) -> None:
        self.config = config
        self.repository = repository

    def simulate_order(
        self,
        workflow_run_id: int,
        signal: PaperSignal,
        risk_state: PaperRiskState,
    ) -> PaperTradeResult:
        if not risk_state.approved:
            return PaperTradeResult(
                status=risk_state.status,
                asset=signal.asset,
                direction=signal.direction,
                reasons=[risk_state.reason],
                warnings=risk_state.warnings,
            )

        fill_price = self._fill_price(signal)
        if fill_price is None or risk_state.approved_size <= 0:
            reason = "No persisted latest price or approved size is available for simulated fill."
            self.repository.store_risk_event(
                workflow_run_id=workflow_run_id,
                asset=signal.asset,
                event_type="PAPER_SIMULATED_FILL",
                status="REJECTED",
                reason=reason,
                details={"simulated_only": True},
            )
            return PaperTradeResult(
                status="REJECTED",
                asset=signal.asset,
                direction=signal.direction,
                reasons=[reason],
                warnings=signal.warnings,
            )

        order = PaperOrder(
            workflow_run_id=workflow_run_id,
            asset=signal.asset,
            direction=signal.direction,
            order_type="MARKET_SIMULATED",
            status="FILLED",
            signal_source=signal.signal_source,
            intended_entry=fill_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            risk_pct=signal.risk_pct,
            size=risk_state.approved_size,
            reasons=[
                *signal.reasons,
                "SIMULATED ORDER filled locally from persisted market snapshot price.",
                "NO REAL EXECUTION.",
            ],
            warnings=signal.warnings,
        )
        order_id = self.repository.store_order(workflow_run_id, order)
        position = PaperPosition(
            workflow_run_id=workflow_run_id,
            order_id=order_id,
            asset=signal.asset,
            direction=signal.direction,
            entry_price=fill_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            size=risk_state.approved_size,
            status="OPEN",
            reasons=[
                "PAPER TRADE position opened by local simulator only.",
                "NO REAL TRADING.",
            ],
        )
        position_id = self.repository.create_position(workflow_run_id, order_id, position)
        return PaperTradeResult(
            status="OPENED",
            asset=signal.asset,
            direction=signal.direction,
            order_id=order_id,
            position_id=position_id,
            entry_price=fill_price,
            size=risk_state.approved_size,
            reasons=order.reasons,
            warnings=order.warnings,
        )

    def update_open_positions(self, workflow_run_id: int) -> list[PaperTradeResult]:
        results: list[PaperTradeResult] = []
        for position in self.repository.fetch_open_positions():
            latest_price = self.repository.fetch_latest_market_price(position.asset)
            if latest_price is None:
                reason = "No latest persisted price exists; simulated position remains open."
                self.repository.store_risk_event(
                    workflow_run_id=workflow_run_id,
                    asset=position.asset,
                    event_type="PAPER_POSITION_UPDATE",
                    status="SKIPPED",
                    reason=reason,
                    details={"position_id": position.id, "simulated_only": True},
                )
                results.append(
                    PaperTradeResult(
                        status="UNCHANGED",
                        asset=position.asset,
                        direction=position.direction,
                        position_id=position.id,
                        reasons=[reason],
                    )
                )
                continue

            close_status = self._close_status(position, latest_price)
            if close_status is None:
                results.append(
                    PaperTradeResult(
                        status="UNCHANGED",
                        asset=position.asset,
                        direction=position.direction,
                        position_id=position.id,
                        exit_price=latest_price,
                        pnl_abs=unrealized_pnl_for_position(position, latest_price),
                        reasons=["Stop loss/take profit not hit; simulated position remains open."],
                    )
                )
                continue

            trade_id, pnl_abs, pnl_pct = self.repository.close_position(
                workflow_run_id=workflow_run_id,
                position=position,
                exit_price=latest_price,
                status=close_status,
                reasons=[
                    f"Simulated {close_status} triggered by latest persisted price {latest_price}.",
                    "NO REAL EXECUTION.",
                ],
            )
            results.append(
                PaperTradeResult(
                    status=close_status,
                    asset=position.asset,
                    direction=position.direction,
                    order_id=position.order_id,
                    position_id=position.id,
                    exit_price=latest_price,
                    pnl_abs=pnl_abs,
                    pnl_pct=pnl_pct,
                    reasons=[f"Stored simulated trade result {trade_id}."],
                )
            )
        return results

    def store_equity_curve_snapshot(self) -> int:
        realized_pnl = self.repository.realized_pnl_total()
        unrealized_pnl = 0.0
        for position in self.repository.fetch_open_positions():
            latest_price = self.repository.fetch_latest_market_price(position.asset)
            unrealized_pnl += unrealized_pnl_for_position(position, latest_price)

        equity = self.config.starting_equity + realized_pnl + unrealized_pnl
        previous_peak = self.repository.peak_equity(self.config.starting_equity)
        peak = max(previous_peak, equity)
        drawdown_pct = ((peak - equity) / peak) * 100 if peak else 0.0
        return self.repository.store_equity_curve(
            equity=equity,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            drawdown_pct=drawdown_pct,
        )

    def _fill_price(self, signal: PaperSignal) -> float | None:
        latest_price = self.repository.fetch_latest_market_price(signal.asset)
        if latest_price is not None:
            return latest_price
        return signal.intended_entry

    @staticmethod
    def _close_status(position: PaperPosition, latest_price: float) -> str | None:
        if position.direction == "LONG":
            if position.stop_loss is not None and latest_price <= position.stop_loss:
                return "CLOSED_STOP_LOSS"
            if position.take_profit is not None and latest_price >= position.take_profit:
                return "CLOSED_TAKE_PROFIT"
            return None

        if position.stop_loss is not None and latest_price >= position.stop_loss:
            return "CLOSED_STOP_LOSS"
        if position.take_profit is not None and latest_price <= position.take_profit:
            return "CLOSED_TAKE_PROFIT"
        return None
