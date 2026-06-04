# AI Trading Firm

## Objective

Build a research-first AI trading workflow for Gold and BTC.

- Start with daily Telegram reporting.
- Add read-only data ingestion.
- Add deterministic scoring.
- Later add paper trading.
- Real execution is explicitly out of scope until later phases.

## Safety Principles

- Research/reporting first.
- No real trade execution in Phase 1.x.
- No order routing.
- No MT5 order sending.
- No private exchange API trading.
- All current integrations are read-only.
- `risk.execution_enabled` must remain `false`.
- Paper trading, when enabled, must remain simulated-only and locally persisted.
- Daily brief must continue even when data is incomplete.
- Never print secrets.

## Completed Phases

### Phase 1.0 MVP

- Project bootstrap
- Config
- SQLite persistence
- Placeholder Gold/BTC bots
- Telegram daily brief
- `DRY_RUN` fallback

### Phase 1.1 Hardening

- `.env` handling
- Config validation
- CLI modes
- Telegram test mode
- Telegram error handling
- Windows batch runner
- Basic tests

### Phase 1.2 Read-Only Market Data

- BTC public price fetch
- Alternative.me Fear & Greed fetch
- Gold macro placeholders
- Data Quality Bot
- Market snapshot persistence
- System Health section

### Phase 1.3 Scoring Engine

- Deterministic rule-based scoring engine
- Standard score result model
- BTC scoring from price + Fear & Greed
- Gold placeholder scoring
- Confidence
- Data completeness
- Score component breakdown
- Score snapshot persistence
- Risk Officer considers low confidence/data completeness

### Phase 1.4 FRED Gold Macro Integration

- Optional `FRED_API_KEY`
- Read-only FRED service
- FRED-based US10Y, real yield, Fed Funds, and CPI ingestion
- Gold macro snapshots persisted
- Gold scoring can use live read-only macro data when available
- Daily brief and data quality remain resilient when FRED is unavailable

### Phase 1.5 BTC Derivatives Read-Only Integration

- Public Binance USD-M Futures funding-rate snapshot
- Public Binance USD-M Futures open-interest snapshot
- BTC derivatives snapshots persisted
- BTC scoring uses funding rate directly when available
- BTC open interest is tracked as context until trend history is added
- BTC confidence is capped at `Medium` until open-interest trend/history logic exists
- System Health includes BTC derivatives data
- Daily brief remains resilient when derivatives endpoints are unavailable

### Phase 1.6 Streamlit Dashboard

- Read-only Streamlit dashboard
- SQLite workflow, market, score, risk, and message monitoring
- Latest daily brief display
- Safety and Risk view with execution disabled
- Windows dashboard launcher
- Lightweight dashboard data-loader tests

### Phase 1.7 Historical Trend Logic

- Dynamic trend analyzer over persisted `market_snapshots`
- BTC trend context for price, Fear & Greed, funding rate, and open interest
- Gold macro trend context for US10Y, real yield, Fed Funds, and CPI
- BTC open-interest trend can unlock higher confidence when valid and clean
- Daily brief includes BTC and Gold trend context
- Streamlit dashboard includes a Trend Context view

### Phase 1.8 Dashboard Charts And Multi-Point Trends

- Multi-point trend summaries from the latest persisted OK snapshots
- Dashboard charts for BTC, Gold macro, and asset scores
- Date range, asset, data type, and row-limit filters
- CSV exports for recent market and score snapshots
- Dashboard remains read-only and monitoring-only

### Phase 1.9 Report Archive And Data Hygiene

- Read-only report archive over workflow runs, daily brief text, and outbound message logs
- Keyword, date range, and status filtering for archived reports/messages
- Dashboard archive preview with TXT/CSV download options
- Data hygiene checks for duplicates, missing recent data, status distribution, gaps, and null/empty values
- Retention policy documented; Phase 1.9 preserves all data and performs no automatic deletion

### Phase 2.0 Paper Trading Engine

- Simulated paper orders only
- `paper_trading.enabled` config flag, disabled by default
- Local SQLite persistence for paper orders, positions, trades, equity curve, and risk events
- Conservative score-based paper signal builder
- Paper risk engine for simulated risk limits and rejections
- Local execution simulator using persisted latest market snapshots only
- `python main.py --paper-run` CLI mode
- Dashboard Paper Trading tab with simulated positions, orders, risk events, and equity curve
- No real trading, no MT5, no private exchange APIs, and no order routing

### Phase 2.1 Paper Trading Review Analytics And Reporting

- Read-only paper analytics over local SQLite paper tables
- Paper performance metrics including equity, P&L, drawdown, win rate, profit factor, and average R-multiple
- Signal review analytics including accepted, rejected, and no-trade summaries
- Persisted paper run summaries for audit and review
- `python main.py --paper-report` local report mode
- Dashboard Paper Trading tab expanded with analytics cards, rejection review, closed positions, and run summaries
- No real trading, no live routing, no MT5, and no private exchange APIs

### Phase 2.2 Paper Signal Tuning And Review Normalization

- Configurable `paper_signal` section with `conservative`, `balanced`, and `exploratory` paper-only profiles
- Paper signal builder thresholds moved out of hardcoded logic and into config/presets
- Normalized `paper_signal_reviews` table for exactly one review outcome per evaluated asset
- Explicit accepted/rejected/no-trade definitions with structured reason codes
- Paper analytics reconcile normalized review counts without double-counting legacy risk events
- Paper run summaries now store the active profile and normalized review totals
- Dashboard and `python main.py --paper-report` show signal tuning, no-trade reasons, and normalized review notes
- No real trading, no live routing, no MT5, and no private exchange APIs

### Phase 2.3 Paper Trade Journal And Review Export

- Local `paper_journal_notes` table for simulated-only review notes
- Read-only CSV export helpers for paper signal reviews, paper run summaries, closed simulated positions, and paper performance summaries
- `python main.py --paper-export` for local review CSV generation into `data/exports`
- Dashboard Paper Trading tab download buttons for review CSVs
- Dashboard Paper Trading tab journal form and recent-note review table
- No real trading, no live routing, no MT5, and no private exchange APIs

### Phase 2.4 Research Data Quality And Market Regime Foundation

- `research_readiness` config section for minimum snapshot history, stale-source thresholds, and decision-readiness scoring
- Read-only market regime classification for BTC and Gold using persisted snapshots and trend analysis only
- Explicit readiness scoring, stale-source review, missing-source review, and no-trade readiness reasons
- Persisted `research_readiness_snapshots` for audit and dashboard history
- Daily brief and `python main.py --paper-report` now include concise readiness summaries
- Dashboard Research Readiness tab with latest readiness cards and recent readiness history
- No real trading, no live routing, no MT5, and no private exchange APIs

### Phase 2.4B Gold Research Input Providers

- Optional read-only `gold_spot_provider` config with environment-only API key loading
- Optional read-only `dxy_provider` config for research monitoring
- Gold spot and DXY snapshots persist into existing `market_snapshots`
- Gold readiness can improve when DXY and Gold spot are configured and healthy
- FRED setup now has clearer environment guidance and startup warnings when `FRED_API_KEY` is missing
- No real trading, no live routing, no MT5, and no private exchange APIs

### Phase 2.5 Strategy Hypothesis Layer

- Deterministic strategy-hypothesis engine built from persisted/read-only research outputs only
- `strategy_hypotheses` config section with enable flag, readiness threshold, minimum confidence, and watch-mode handling
- Persisted `strategy_hypotheses` table for BTC and Gold research hypotheses
- Daily brief includes concise Strategy Hypotheses section
- `python main.py --paper-report` includes latest persisted strategy hypotheses
- Dashboard includes a Strategy Hypotheses tab and recent history view
- No real trading, no live routing, no MT5, and no private exchange APIs

### Phase 2.6 Hypothesis Outcome Tracking

- Deterministic read-only outcome evaluator built from persisted `strategy_hypotheses` and later persisted `market_snapshots` only
- `hypothesis_outcomes` config section with horizon settings, neutral-move thresholds, and maximum lookback window
- Persisted `strategy_hypothesis_outcomes` table with favorable, unfavorable, neutral, insufficient-follow-up, and blocked-not-evaluated classifications
- `python main.py --hypothesis-outcomes` local review mode for matured hypotheses only
- Daily brief and `python main.py --paper-report` now include concise hypothesis-outcome summaries
- Dashboard includes read-only hypothesis-outcome counts, rates, and latest-history tables
- No real trading, no paper order creation, no live routing, no MT5, and no private exchange APIs

### Phase 2.7 Hypothesis Review Analytics

- Deterministic read-only review analytics built from persisted `strategy_hypothesis_outcomes` only
- `hypothesis_review` config section with candidate thresholds and readiness-bucket settings
- Persisted `hypothesis_review_summaries` for dashboard and report review history
- `python main.py --hypothesis-review` local analytics mode
- Daily brief and `python main.py --paper-report` include concise hypothesis-review summaries
- Dashboard shows review-only counts, rates, grouping tables, candidate flags, and warnings
- No real trading, no paper order creation, no live routing, no MT5, and no private exchange APIs

### Phase 2.8 Hypothesis Review Drilldown, Tags, And Export

- Read-only export tooling for `strategy_hypotheses`, `strategy_hypothesis_outcomes`, and `hypothesis_review_summaries`
- `python main.py --hypothesis-review-export` local export mode writing CSV files into `data/exports`
- Local `hypothesis_review_notes` metadata for review tags, notes, and filtered dashboard visibility
- Dashboard drilldown filters for asset, strategy family, regime, horizon, outcome status, readiness bucket, and hypothesis status
- Candidate-progress visibility with `REVIEW_CANDIDATE`, `NEED_MORE_SAMPLES`, `FAIL_RATE_THRESHOLD`, `FAIL_ADVERSE_MOVE`, and `BLOCKED`
- `python main.py --paper-report` and `python main.py --hypothesis-review` now include concise candidate-progress context
- No real trading, no paper order creation, no live routing, no MT5, and no private exchange APIs

### Phase 2.9 Hypothesis Edge Slicing And Stability Review

- Deterministic read-only `hypothesis_edge_slicing` analytics built from persisted `strategy_hypothesis_outcomes` only
- Slicing dimensions for asset, strategy family, regime, horizon, readiness bucket, confidence bucket, and weekday
- Stability classification for `INSUFFICIENT_SAMPLE`, `STRONG_POSITIVE`, `WEAK_POSITIVE`, `NEUTRAL`, `NEGATIVE`, `HIGH_ADVERSE_MOVE`, and `MIXED_OR_UNSTABLE`
- Persisted `hypothesis_edge_slice_summaries` plus optional `hypothesis_edge_slice_rows` for dashboard/report history
- `python main.py --hypothesis-edge-slicing` local analytics mode
- Dashboard edge drilldowns, filtered slice tables, strongest/weakest/unstable slice visibility, and slice-row CSV downloads
- Daily brief, `python main.py --paper-report`, and `python main.py --hypothesis-review` include concise edge-slicing review context
- No real trading, no paper order creation, no live routing, no MT5, and no private exchange APIs

## Current Known Limitations

- Gold macro FRED data depends on `FRED_API_KEY`; without it, FRED inputs stay `NOT_CONFIGURED`.
- DXY and Gold spot providers are optional, disabled by default, and remain `NOT_CONFIGURED` until explicitly configured.
- BTC funding-rate and open-interest scoring remains intentionally simple and rule-based.
- Multi-point trend logic is currently used for dashboard monitoring; scoring remains conservative and deterministic.
- Gold readiness will remain constrained until DXY and Gold spot research inputs are configured and enough snapshot history exists.
- Gold macro freshness can degrade quickly because CPI and Fed Funds are slower-moving series than BTC data.
- Data hygiene checks identify issues but do not repair or compact data automatically.
- Strategy hypotheses are research artifacts only; they are not paper orders, execution signals, or autonomous decisions.
- Hypothesis outcomes are review metrics only; they do not create paper trades, promote hypotheses automatically, or authorize execution.
- Hypothesis review candidates are review flags only; they do not enable paper trading or execution automatically.
- Hypothesis review notes and tags are local metadata only; they do not change hypotheses, scores, or execution permissions.
- Hypothesis edge slices are review heuristics only; they do not promote paper trading, create orders, or authorize execution.
- Paper trading is simulated-only and disabled by default.
- Paper fills use persisted latest snapshot prices, not broker or exchange execution.
- Exploratory paper-signal tuning is available for simulation only and must not be treated as production-ready execution logic.
- `pytest` may not be installed in the current interpreter.
- Dashboard is local Streamlit only; no authentication or hosted deployment yet.
- No live execution.

## Next Recommended Phases

### Phase 1.10

- Consider safe public long/short-ratio or liquidation context only if endpoints are read-only, stable, and clearly documented.
- Keep scoring changes conservative until enough snapshot history exists.
- Consider explicit retention tooling only after approval, with backups and audit logs.

### Phase 2.10

- Consider richer regime or volatility slicing only if persisted review sample size materially improves.
- Consider read-only note editing or richer edge-export tooling only if review volume grows materially.
- Consider later paper forward-testing promotion rules only after more slice stability history exists and after explicit approval.

### Phase 3.0

- Future execution planning only after explicit approval.
- No real order execution without a separate safety review and phase approval.

## Current Recommended Commands

- `python main.py --dry-run`
- `python main.py --send-telegram`
- `python main.py --test-telegram`
- `python main.py --paper-run`
- `python main.py --paper-report`
- `python main.py --paper-export`
- `python main.py --hypothesis-outcomes`
- `python main.py --hypothesis-review`
- `python main.py --hypothesis-review-export`
- `python main.py --hypothesis-edge-slicing`
- `streamlit run dashboard/app.py`
- `python -m compileall .`
- `pytest`

## Strict Warning

- Do not add order execution without explicit phase approval.
- Do not add MT5 `order_send`.
- Do not add Binance private trading endpoints.
- Do not allow LLM-based trade execution.
- Scoring may support research, not automatic execution.
- Paper trading must remain simulated-only until a later explicitly approved phase.
