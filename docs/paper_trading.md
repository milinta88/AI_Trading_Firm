# Phase 2.0 Through 2.4B Paper Trading

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

## Phase 2.4B Gold Research Inputs

Phase 2.4B adds optional read-only Gold DXY and Gold spot inputs for research readiness and report quality only.

- These providers can improve Gold completeness and readiness when configured.
- They do not change paper-trading signal thresholds or simulated execution rules.
- Public/provider data remains research-only and not broker-grade execution data.

## Phase 2.5 Strategy Hypotheses

Phase 2.5 adds a research-only hypothesis layer that sits before any future paper forward-testing review.

- Hypotheses are deterministic and built from score snapshots, research readiness, trend context, market-data health, and data quality.
- Hypotheses persist in the local `strategy_hypotheses` table for dashboard and report review.
- `python main.py --paper-report` can now show the latest persisted BTC and Gold strategy hypotheses.
- Hypotheses do not create simulated orders by themselves and do not change paper signal thresholds.

## Phase 2.6 Hypothesis Outcome Tracking

Phase 2.6 adds a read-only review layer that compares persisted strategy hypotheses with later persisted market snapshots.

- Outcomes are evaluated from local SQLite only and use no live execution, broker, MT5, or private exchange API path.
- `strategy_hypothesis_outcomes` stores horizon-based review rows for `4h`, `24h`, and `72h`.
- Outcomes classify persisted hypotheses as `FAVORABLE`, `UNFAVORABLE`, `NEUTRAL`, `INSUFFICIENT_FOLLOWUP_DATA`, or `BLOCKED_NOT_EVALUATED`.
- `python main.py --hypothesis-outcomes` evaluates matured hypotheses without creating paper orders or modifying paper signal thresholds.
- `python main.py --paper-report` and the dashboard can now summarize the latest persisted hypothesis outcomes for review only.

## Phase 2.7 Hypothesis Review Analytics

Phase 2.7 adds a higher-level read-only analytics layer over persisted hypothesis outcomes.

- Review analytics summarize favorable, unfavorable, neutral, insufficient-follow-up, and blocked outcomes.
- Grouping is available by asset, strategy family, regime, horizon, readiness bucket, and hypothesis status.
- Candidate flags are review-only and require minimum sample size plus favorable/unfavorable/adverse-move thresholds.
- `python main.py --hypothesis-review` builds and optionally persists local review summaries without creating paper orders.
- `python main.py --paper-report` and the dashboard can summarize the latest persisted review analytics for research-only review.

## Phase 2.8 Hypothesis Review Drilldown, Tags, And Export

Phase 2.8 adds practical review tooling around the persisted hypothesis review layer.

- `python main.py --hypothesis-review-export` writes local CSV exports for hypotheses, hypothesis outcomes, and review summaries into `data/exports`.
- Dashboard review drilldowns can slice persisted outcomes by asset, strategy family, regime, horizon, outcome status, readiness bucket, and hypothesis status.
- Candidate-progress rows show whether a family is a `REVIEW_CANDIDATE`, still needs more samples, fails rate thresholds, fails adverse-move thresholds, or remains blocked.
- Local `hypothesis_review_notes` store optional review tags and notes only; they do not create paper orders or change paper-trading thresholds.
- All tooling remains review-only, local-only, and free of broker, MT5, private exchange API, or real execution behavior.
