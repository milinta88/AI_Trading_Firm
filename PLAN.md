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

## Current Known Limitations

- Gold macro FRED data depends on `FRED_API_KEY`; without it, FRED inputs stay `NOT_CONFIGURED`.
- DXY is still `NOT_CONFIGURED`.
- Gold spot price is still `NOT_CONFIGURED`.
- BTC funding-rate and open-interest scoring remains intentionally simple and rule-based.
- Multi-point trend logic is currently used for dashboard monitoring; scoring remains conservative and deterministic.
- Data hygiene checks identify issues but do not repair or compact data automatically.
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

### Phase 2.4

- Consider richer paper position lifecycle rules after more snapshot history exists.
- Consider paper performance slicing by regime, profile, or signal family using persisted local data only.
- Consider read-only review tagging/filtering refinements for journal notes and exports if usage grows.

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
