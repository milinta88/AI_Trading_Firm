# Phase 2.0 Through 2.4 Paper Trading

Paper trading is simulated only. It does not send real orders, connect to MT5, call `order_send`, use exchange API keys, or touch private trading endpoints.

## Safety Rules

- `risk.execution_enabled` must remain `false`.
- `paper_trading.enabled` is `false` by default.
- Simulated fills use persisted SQLite market snapshots only.
- All paper orders, positions, trades, equity snapshots, and risk events stay local in SQLite.
- Paper outputs must be labeled as `PAPER TRADE`, `SIMULATED ORDER`, and `NO REAL EXECUTION` where applicable.

## Config

```yaml
paper_trading:
  enabled: false
  starting_equity: 10000
  base_currency: USD
  max_risk_per_trade_pct: 0.25
  max_daily_loss_pct: 1.0
  max_open_positions: 2
  allow_long: true
  allow_short: true
  fill_mode: close_price

paper_signal:
  profile: conservative
  btc_long_score_threshold: 70
  btc_short_score_threshold: 35
  gold_long_score_threshold: 70
  gold_short_score_threshold: 35
  min_confidence: Medium
  min_btc_data_completeness: 80
  min_gold_data_completeness: 60
  allow_neutral_bias: false
  exploratory_mode: false
```

## Paper Signal Profiles

- `conservative`: closest to the original paper-signal rules and remains the safest default profile.
- `balanced`: slightly relaxes simulated score/data thresholds while remaining paper-only.
- `exploratory`: allows more simulated candidates, can allow neutral bias, and must be treated as experimental paper-only tuning.

All profiles remain simulated-only. They do not enable real orders, live routing, MT5, or private exchange APIs.

## How Paper Positions Are Created

1. Run `python main.py --paper-run`.
2. The normal research daily brief runs first.
3. If `paper_trading.enabled` is `false`, the paper run logs that it is disabled and exits.
4. If enabled, the paper orchestrator reads latest score snapshots and latest persisted market prices.
5. The signal builder reads the active `paper_signal` profile and creates a paper candidate or `NO_TRADE`.
6. The paper risk engine applies simulated risk limits.
7. The execution simulator stores local simulated orders and positions only.

## Dashboard

Run:

```powershell
streamlit run dashboard/app.py
```

Open the Paper Trading tab to review:

- Enabled/disabled status
- Latest paper equity
- Open simulated positions
- Recent simulated orders
- Paper risk events and rejections
- Paper equity curve

The dashboard is monitoring-only for paper trading state. Phase 2.3 journal notes add local review metadata only.

## Phase 2.1 Review Analytics

Phase 2.1 adds read-only analytics and reporting on top of the simulated-only engine.

- `paper_trading/analytics.py` reads local SQLite paper tables only.
- `paper_run_summaries` stores per-run paper review summaries for audit.
- `reports/paper_report.py` formats a local-only `PAPER TRADING REPORT` with `SIMULATED ONLY` and `NO REAL EXECUTION` labels.
- `python main.py --paper-report` prints the latest local paper analytics summary without running the research workflow or any simulation.

## Phase 2.1 Metrics

The paper analytics layer calculates:

- Starting equity
- Latest equity
- Total P&L and total P&L %
- Max drawdown %
- Total orders
- Open positions
- Closed positions
- Total trades
- Winning and losing trades
- Win rate
- Gross profit and gross loss
- Profit factor
- Average P&L
- Average R-multiple when enough closed-trade data exists

## Signal Review

Phase 2.2 normalizes signal review into `paper_signal_reviews` so every evaluated asset gets exactly one review outcome:

- `ACCEPTED`: the signal met paper-signal builder rules and passed the paper risk engine.
- `REJECTED`: the signal met paper-signal builder rules but the paper risk engine rejected it.
- `NO_TRADE`: the paper-signal builder rules were not met, so no simulated order was attempted.

Normalized review rows store non-secret audit context including:

- `workflow_run_id`
- `asset`
- `signal_action`
- `review_status`
- `bias`
- `total_score`
- `confidence`
- `data_completeness`
- `active_profile`
- `reasons_json`
- `warnings_json`
- `created_at`

Paper analytics now prefer `paper_signal_reviews` and summarize:

- Signals evaluated
- Signals accepted
- Signals rejected
- No-trade count
- Accepted by asset
- Rejected by asset
- No-trade by asset
- Rejections by reason
- No-trade by reason
- Accepted by profile
- No-trade by profile

Reason summaries are occurrence-based. A single normalized review can contribute multiple reason codes, so per-reason totals may exceed the number of accepted/rejected/no-trade reviews.

Legacy `paper_risk_events` remain useful for detailed risk audit trails. When normalized signal reviews exist, analytics ignore legacy signal-risk events for count reconciliation so accepted/rejected/no-trade totals do not get double-counted.

## Expanded Dashboard Review

Phase 2.1 and 2.2 expand the Paper Trading tab with:

- Performance metric cards
- Latest paper run summary
- Closed simulated positions table
- Signal review summary
- Signal tuning summary with the active profile and thresholds
- Rejection reasons chart
- No-trade reasons chart
- Normalized signal review table with asset/profile/status filters
- P&L by asset chart
- Recent persisted paper run summaries

All dashboard views remain monitoring-only for paper trading state; journal notes remain local review metadata only.

## Phase 2.3 Paper Trade Journal And Review Export

Phase 2.3 adds lightweight review tooling without changing paper-trading decision logic.

- `paper_trading/export_service.py` creates safe local CSV exports from SQLite only.
- Export targets include `paper_signal_reviews`, `paper_run_summaries`, closed simulated positions, and paper performance summaries.
- `python main.py --paper-export` writes timestamped `paper_signal_reviews_*.csv` and `paper_run_summaries_*.csv` files into `data/exports`.
- Dashboard download buttons expose paper signal reviews, paper run summaries, and closed simulated trades when available.

## Paper Journal Notes

Journal notes are local review metadata only. They do not change simulated orders, positions, scores, thresholds, or risk decisions.

The `paper_journal_notes` table stores:

- `note_type`
- `reference_id`
- `asset`
- `profile`
- `title`
- `note_text`
- `tags`
- `created_at`
- `updated_at`
- `is_deleted`

Supported note types include:

- `GENERAL`
- `RUN`
- `SIGNAL_REVIEW`
- `TRADE`

Repository helpers support insert, list, update, and soft-delete operations for local review workflows only.

## Dashboard Review Tools

The Paper Trading tab now includes:

- Review CSV download buttons
- A lightweight paper journal note form
- A recent journal-notes table

These tools are for simulated-only review and audit support. They do not enable real trading, order routing, broker connectivity, MT5, or private exchange APIs.

## Phase 2.4 Research Readiness Support

Phase 2.4 does not change simulated order logic. It adds a research-readiness layer that `python main.py --paper-report` can summarize alongside paper analytics.

- Readiness uses persisted market snapshots and existing trend analysis only.
- Regime classification is read-only and asset-specific.
- Readiness can mark an asset as not decision-ready because of missing data, stale data, or insufficient snapshot history.
- These readiness summaries are for research quality control, not live execution.
