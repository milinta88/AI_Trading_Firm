# AI Trading Firm

Phase 1 MVP for a research-first trading workflow that produces a daily Telegram brief for Gold and BTC.

Phase 1.2 adds read-only public market data for research/reporting while keeping execution fully disabled.
Phase 1.3 adds a deterministic scoring engine with component breakdowns, confidence, and data completeness.
Phase 1.4 adds optional read-only FRED macro integration for Gold while keeping execution fully disabled.
Phase 1.5 adds read-only BTC derivatives integration for funding rate and open interest using public endpoints only.
Phase 1.6 adds a read-only Streamlit dashboard for monitoring reports, snapshots, scores, and safety status.
Phase 1.7 adds historical trend logic using persisted SQLite market snapshots only.
Phase 1.8 adds dashboard charts, filters, CSV exports, and multi-point trend summaries from persisted snapshots.
Phase 1.9 adds report archive search, review tools, and read-only data hygiene checks.
Phase 2.0 adds a simulated-only paper trading engine with local SQLite orders, positions, trades, equity, and risk events.
Phase 2.1 adds read-only paper trading review analytics, signal review summaries, run summaries, and local text reporting.
Phase 2.2 adds configurable paper signal tuning profiles and normalized signal-review analytics for clean accepted/rejected/no-trade reconciliation.
Phase 2.3 adds paper trade journal notes and local CSV review exports for simulated-only review workflows.
Phase 2.4 adds market regime classification, research readiness scoring, and explicit no-trade readiness reasons from persisted snapshots only.
Phase 2.4B adds optional read-only Gold spot and DXY provider inputs plus clearer macro-provider setup guidance.
Phase 2.5 adds a deterministic strategy hypothesis layer for research review, persistence, dashboard monitoring, and later paper-forward-testing preparation.
Phase 2.6 adds read-only hypothesis outcome tracking that reviews persisted hypotheses against later persisted market snapshots only.
Phase 2.7 adds read-only hypothesis review analytics so we can summarize early edge by asset, family, regime, horizon, and readiness bucket before any future paper-forward-test promotion.

This project still does not execute real trades. It does not route live orders, connect to MT5, or connect to private exchange APIs.

See [PLAN.md](</C:/Users/saroj/Documents/New project/AI_Trading_Firm/PLAN.md>) for the living roadmap, completed phases, and next recommended milestones.

## Scope

- Research mode only
- No real trade execution
- No order routing or exchange connectivity
- No MT5 connectivity
- No exchange private API connectivity
- No real buy/sell order capability
- Read-only public market data only
- Simulated paper trading only when explicitly enabled
- Placeholder analysis bots with safe fallback behavior
- SQLite persistence for workflow runs and message logs

## Phase 1.2 Highlights

- Read-only BTCUSDT public price fetch
- Read-only Alternative.me Fear & Greed Index fetch
- Gold macro placeholders for future FRED integration
- Data Quality Bot that marks sources as `OK`, `FAIL`, `NOT_CONFIGURED`, or `STALE`
- Market snapshots persisted in SQLite
- Daily brief continues running even if external APIs fail

## Phase 1.3 Scoring Engine

- Deterministic rule-based scoring only
- No LLM-based trading decisions
- Standard score outputs include total score, bias, confidence, data completeness, component breakdown, and warnings.
- Score snapshots persisted in SQLite
- Risk Officer now considers confidence and data completeness
- Daily brief includes concise score breakdown sections for Gold and BTC

## Phase 1.4 FRED Macro Integration

- Optional `FRED_API_KEY` environment variable for read-only macro data
- Read-only FRED service for latest macro observations
- Initial configured series: US10Y, 10Y real yield, Fed Funds, and CPI
- Gold macro snapshots persisted in SQLite
- Gold scoring can use live read-only macro data when available
- Daily brief still completes safely if FRED is missing, stale, or unavailable

## Phase 1.5 BTC Derivatives Integration

- Read-only Binance USD-M Futures funding-rate snapshot via a public endpoint
- Read-only Binance USD-M Futures open-interest snapshot via a public endpoint
- BTC derivatives snapshots persisted in SQLite
- BTC scoring now uses funding rate directly and tracks open interest as context
- System Health includes a dedicated BTC derivatives status
- Daily brief still completes safely if derivatives endpoints fail or become unavailable

## Phase 1.6 Streamlit Dashboard

- Read-only dashboard over the existing SQLite database
- Shows latest workflow status, market snapshots, scores, risk status, report text, and message logs
- Includes Safety and Risk view with `EXECUTION DISABLED` and `WATCH ONLY`
- Handles missing database or missing tables gracefully
- Does not fetch new trading data, mutate state, route orders, or execute trades

## Phase 1.7 Historical Trend Logic

- Dynamic trend analysis over persisted `market_snapshots`
- No new market-data endpoints and no state mutation
- BTC trends cover price, Fear & Greed, funding rate, and open interest
- Gold macro trends cover US10Y, real yield, Fed Funds, and CPI
- BTC confidence can become `High` only when open-interest trend history is valid and no major warnings exist
- Daily brief and dashboard include concise trend context

## Phase 1.8 Dashboard Charts And Multi-Point Trends

- Streamlit dashboard charts for BTC price, Fear & Greed, funding rate, open interest, Gold US10Y, Gold real yield, and asset scores
- Dashboard filters for date range, asset, data type, and row limits
- CSV downloads for recent market snapshots and score snapshots
- Multi-point trend summaries use the latest persisted OK snapshots without fetching new data
- Dashboard remains read-only and monitoring-only

## Phase 1.9 Report Archive And Data Hygiene

- Read-only report archive over stored workflow runs, daily brief text, and Telegram/message logs
- Archive search by keyword, date range, and status
- Dashboard report preview with TXT and CSV download options
- Data hygiene checks for duplicate snapshots, missing recent data, status distribution, data gaps, and null/empty values
- Hygiene checks provide suggested actions but never delete, compact, or mutate data

## Phase 2.0 Paper Trading

- Simulated orders only; no real order routing, MT5 `order_send`, exchange API keys, or private trading endpoints
- Disabled by default with `paper_trading.enabled: false`
- Stores simulated orders, positions, trades, equity curve, and risk events in SQLite
- Builds conservative paper signals from existing score snapshots and persisted market prices
- Enforces paper-only risk checks such as max risk per trade, max daily loss, max open positions, and long/short permissions
- Dashboard includes a Paper Trading tab clearly labeled `SIMULATED ONLY`

## Phase 2.1 Paper Trading Analytics

- Read-only analytics over local SQLite paper tables only
- Tracks latest equity, total P&L, drawdown, win rate, profit factor, average P&L, and average R-multiple
- Summarizes signal review outcomes including accepted, rejected, and no-trade counts
- Persists paper run summaries for workflow review and audit
- Adds `python main.py --paper-report` for a local text-only simulated-paper report
- Expands the dashboard Paper Trading tab with analytics cards, rejection summaries, closed-position review, and run summaries

## Phase 2.2 Paper Signal Tuning And Review Normalization

- Adds configurable `paper_signal` tuning with `conservative`, `balanced`, and `exploratory` paper-only profiles
- Moves paper-signal score, confidence, and data-completeness thresholds into config
- Persists normalized `paper_signal_reviews` so each evaluated asset becomes exactly one `ACCEPTED`, `REJECTED`, or `NO_TRADE` review row
- Reconciles paper analytics cleanly: `signals_evaluated = signals_accepted + signals_rejected + no_trade_count`
- Dashboard and `python main.py --paper-report` now show active profile, tuning summary, no-trade reasons, and normalized review notes
- Legacy `paper_risk_events` remain available for audit, but normalized review analytics avoid double-counting them

## Phase 2.3 Paper Trade Journal And Review Export

- Adds a simulated-only paper trade journal stored locally in SQLite
- Adds safe CSV export helpers for `paper_signal_reviews`, `paper_run_summaries`, closed simulated positions, and paper performance summaries
- Adds `python main.py --paper-export` to write local review CSVs into `data/exports`
- Adds dashboard download buttons for paper signal reviews, run summaries, and closed simulated trades when available
- Keeps exports local, read-only with respect to trading logic, and free of secrets

## Phase 2.4 Research Data Quality And Market Regime Foundation

- Adds persisted-snapshot research readiness scoring for BTC and Gold
- Adds market regime classification using only existing trend analysis and stored market snapshots
- Adds explicit no-trade readiness reasons when snapshot history, freshness, or completeness is insufficient
- Persists `research_readiness_snapshots` for dashboard review history
- Adds a dashboard Research Readiness tab plus concise readiness sections in the daily brief and `python main.py --paper-report`
- Does not add new execution, broker connectivity, order routing, or strategy auto-ordering

## Phase 2.4B Gold Research Input Providers

- Adds optional read-only `gold_spot_provider` and `dxy_provider` config sections
- Gold spot uses a configurable `goldapi_io` provider with the API key kept in the environment only
- DXY uses a read-only Yahoo Finance quote path for research monitoring only
- Both providers are disabled by default and return `NOT_CONFIGURED` until explicitly enabled
- Daily brief, dashboard, and research readiness keep running safely if these providers are disabled, stale, or unavailable
- These sources are research-only and not broker-grade execution data

## Phase 2.5 Strategy Hypothesis Layer

- Adds deterministic `strategy_hypotheses` config for research-only hypothesis generation
- Maps score snapshots, research readiness, regime, trend context, market-data health, and data quality into persisted research hypotheses
- Persists `strategy_hypotheses` rows for BTC and Gold after the normal daily workflow
- Adds a concise `Strategy Hypotheses` section to the daily brief and `python main.py --paper-report`
- Adds a dashboard Strategy Hypotheses tab for latest hypotheses and recent history
- Does not create orders, broker signals, MT5 requests, private exchange API calls, or automatic execution

## Phase 2.6 Hypothesis Outcome Tracking

- Adds deterministic `hypothesis_outcomes` config for read-only forward review at `4h`, `24h`, and `72h` horizons
- Evaluates persisted `strategy_hypotheses` against later persisted `market_snapshots` only
- Persists `strategy_hypothesis_outcomes` with `FAVORABLE`, `UNFAVORABLE`, `NEUTRAL`, `INSUFFICIENT_FOLLOWUP_DATA`, or `BLOCKED_NOT_EVALUATED`
- Adds `python main.py --hypothesis-outcomes` for local outcome evaluation without running trading or paper execution
- Daily brief, `python main.py --paper-report`, and the dashboard now include concise hypothesis-outcome review sections
- Does not create orders, paper trades, broker requests, MT5 requests, private exchange API calls, or automatic execution

## Phase 2.7 Hypothesis Review Analytics

- Adds deterministic `hypothesis_review` config for read-only review thresholds and readiness buckets
- Summarizes persisted `strategy_hypothesis_outcomes` by asset, strategy family, regime, horizon, readiness bucket, and hypothesis status
- Flags `REVIEW_CANDIDATE` families only when minimum sample size, favorable-rate, unfavorable-rate, and adverse-move thresholds are met
- Persists `hypothesis_review_summaries` for dashboard/report review history
- Adds `python main.py --hypothesis-review` for local review analytics without running trading or paper execution
- Daily brief, `python main.py --paper-report`, and the dashboard now include concise hypothesis-review summary sections
- Does not create orders, paper trades, broker requests, MT5 requests, private exchange API calls, or automatic execution

## Phase 2.8 Hypothesis Review Drilldown, Tags, And Export

- Adds read-only CSV export tooling for `strategy_hypotheses`, `strategy_hypothesis_outcomes`, and `hypothesis_review_summaries`
- Adds `python main.py --hypothesis-review-export` to write local review CSV files into `data/exports`
- Adds local `hypothesis_review_notes` metadata with tags, filters, and recent-note visibility in the dashboard
- Adds dashboard drilldown filters for asset, strategy family, regime, horizon, outcome status, readiness bucket, and hypothesis status
- Adds candidate-progress visibility with `REVIEW_CANDIDATE`, `NEED_MORE_SAMPLES`, `FAIL_RATE_THRESHOLD`, `FAIL_ADVERSE_MOVE`, or `BLOCKED`
- Updates `python main.py --hypothesis-review` and `python main.py --paper-report` with concise candidate-progress context
- Does not create orders, paper trades, broker requests, MT5 requests, private exchange API calls, or automatic execution

## Windows Setup

1. Open PowerShell in the project folder:

```powershell
cd "C:\Users\saroj\Documents\New project\AI_Trading_Firm"
```

2. Create a virtual environment:

```powershell
python -m venv .venv
```

3. Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

4. Install dependencies:

```powershell
pip install -r requirements.txt
```

## Create `.env`

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and add Telegram credentials only if you want live message delivery:

```dotenv
TELEGRAM_BOT_TOKEN=123456:your_bot_token_here
TELEGRAM_CHAT_ID=123456789
FRED_API_KEY=your_fred_api_key_here
GOLD_API_KEY=your_gold_spot_provider_key_here
APP_MODE=research
LOG_LEVEL=INFO
```

If `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` is missing, the app automatically stays in `DRY_RUN` mode and logs the message locally instead of sending it.
If `FRED_API_KEY` is missing, FRED macro sources stay `NOT_CONFIGURED`, the app logs a startup warning, and the daily brief continues in research mode.
If `GOLD_API_KEY` is missing, the optional Gold spot provider stays `NOT_CONFIGURED`.

## Optional Gold Research Providers

These providers are read-only and disabled by default.

```yaml
gold_spot_provider:
  enabled: false
  provider: goldapi_io
  url: ""
  api_key_env: GOLD_API_KEY
  timeout_seconds: 10

dxy_provider:
  enabled: false
  provider: yahoo_finance
  symbol: DX-Y.NYB
  timeout_seconds: 10
```

Notes:
- `gold_spot_provider.url` is left blank by default so no third-party spot-price call is made until you explicitly configure one.
- DXY via Yahoo Finance is for research monitoring only and may be delayed; it is not broker-grade execution data.
- Enabling these providers does not enable trading, order routing, MT5, or private exchange APIs.

## Run The App

Default run:

```powershell
python main.py
```

Forced dry-run:

```powershell
python main.py --dry-run
```

Live Telegram daily brief:

```powershell
python main.py --send-telegram
```

Telegram connectivity test only:

```powershell
python main.py --test-telegram
```

Paper trading run:

```powershell
python main.py --paper-run
```

Read-only paper analytics report:

```powershell
python main.py --paper-report
```

Paper review export:

```powershell
python main.py --paper-export
```

Read-only hypothesis outcome review:

```powershell
python main.py --hypothesis-outcomes
```

Read-only hypothesis review analytics:

```powershell
python main.py --hypothesis-review
```

Read-only hypothesis review export:

```powershell
python main.py --hypothesis-review-export
```

Read-only dashboard:

```powershell
streamlit run dashboard/app.py
```

Windows dashboard launcher:

```powershell
run_dashboard.bat
```

The safest routine for scheduled reporting is still:

```powershell
python main.py --dry-run
```

## CLI Behavior

- `python main.py` runs the daily brief once. If Telegram credentials exist, it can send live. If they do not exist, it falls back to `DRY_RUN`.
- `python main.py --dry-run` never sends Telegram, even if credentials exist.
- `python main.py --send-telegram` sends the daily brief if credentials exist. If credentials are missing, it stays in `DRY_RUN`.
- `python main.py --test-telegram` sends a short test message only. If credentials are missing, it stays in `DRY_RUN` and does not crash.
- `python main.py --paper-run` runs the normal daily brief first, then runs the paper trading orchestrator only when `paper_trading.enabled` is `true`.
- `python main.py --paper-report` prints a local text-only paper trading review report from SQLite and does not run the workflow or simulation.
- `python main.py --paper-export` writes local paper review CSV files into `data/exports` and does not run the workflow or simulation.
- `python main.py --hypothesis-outcomes` evaluates matured persisted strategy hypotheses against later persisted market snapshots only and does not run trading or paper execution.
- `python main.py --hypothesis-review` summarizes persisted hypothesis outcomes into read-only review analytics and does not run trading or paper execution.
- `python main.py --hypothesis-review-export` writes local hypothesis-review CSV files into `data/exports` and does not run trading, paper execution, or workflow delivery.

## Read-Only Market Data

Phase 1.2 through Phase 1.9 use read-only endpoints and persisted snapshots only.

- BTC price uses a public Binance ticker endpoint.
- Fear & Greed uses the public Alternative.me API.
- BTC funding rate uses Binance's public USD-M Futures mark-price endpoint.
- BTC open interest uses Binance's public USD-M Futures open-interest endpoint.
- Open interest trend is computed from persisted snapshots when enough history exists.
- Multi-point trend summaries are computed from persisted snapshots only.
- BTC confidence can rise above `Medium` only when persisted open-interest trend logic is available and clean.
- Gold macro inputs can use optional read-only FRED series.
- DXY can use an optional read-only Yahoo Finance quote path.
- Gold spot can use an optional read-only Gold spot provider keyed only through environment variables.
- DXY and Gold spot remain `NOT_CONFIGURED` until those optional providers are explicitly enabled and configured.

If any external API fails, times out, returns invalid JSON, or becomes unavailable, the daily brief still completes and records the missing source as unavailable instead of crashing.

## Dashboard

The dashboard reads from SQLite only and is intended for monitoring generated reports and persisted snapshots.

```powershell
streamlit run dashboard/app.py
```

You can also use [run_dashboard.bat](<C:/Users/saroj/Documents/New project/AI_Trading_Firm/run_dashboard.bat>) on Windows. Run `python main.py --dry-run` first if the database has not been created yet.

Dashboard Phase 1.8 features include native Streamlit charts, date/asset/data-type filters, row-limit controls, multi-point trend context, and CSV exports for recent market and score snapshots. Phase 1.9 adds report archive search and data hygiene tabs. Trading and workflow state remain read-only in the dashboard; Phase 2.3 adds local journal-note review metadata only.
Phase 2.0 adds a Paper Trading tab for simulated-only local orders, open positions, risk events, and paper equity curve. Phase 2.1 expands that tab with paper performance metrics, signal review summaries, rejection charts, closed-position review, and persisted paper run summaries.
Phase 2.2 adds profile-aware paper signal tuning, normalized signal-review tables, no-trade reason charts, and profile/status filters for recent review rows.
Phase 2.3 adds local paper-review CSV downloads plus a lightweight journal form and recent-notes table for simulated-only review notes.
Phase 2.8 adds hypothesis-review drilldowns, candidate-progress tables, review tags/notes, filtered outcome CSV downloads, and local hypothesis-review export support.
Phase 2.4 adds a Research Readiness tab with BTC/Gold readiness cards, regime summaries, missing/stale source review, and persisted readiness history.
Phase 2.6 adds read-only Strategy Hypothesis Outcome summaries, latest outcome tables, and favorable/unfavorable rate views built only from persisted hypotheses and persisted market snapshots.
Phase 2.7 adds read-only Strategy Hypothesis Review analytics with candidate flags, readiness-bucket summaries, regime/family breakdowns, and persisted review-summary history.

See [docs/paper_trading.md](</C:/Users/saroj/Documents/New project/AI_Trading_Firm/docs/paper_trading.md>) for the paper trading design and safety rules.

## Retention Policy

Phase 1.9 does not delete data automatically.

- Current policy: preserve all workflow runs, market snapshots, score snapshots, and outbound message logs.
- Future option: archive old snapshots to a separate file after explicit approval.
- Future option: compact duplicate snapshots after explicit approval and audit review.
- Future option: keep all snapshots permanently if storage remains manageable.

Any future retention or compaction feature must remain separate from trading execution and must not remove audit data without explicit phase approval.

## Windows Task Scheduler

The project includes [run_daily_brief.bat](<C:/Users/saroj/Documents/New project/AI_Trading_Firm/run_daily_brief.bat>) for scheduled runs.

1. Open Task Scheduler.
2. Create a new basic task.
3. Pick your preferred daily schedule.
4. Set the action to start a program.
5. Choose the batch file: [run_daily_brief.bat](<C:/Users/saroj/Documents/New project/AI_Trading_Firm/run_daily_brief.bat>).
6. Make sure the task starts in the project folder if your environment requires it.
7. Confirm that `.env` exists before the scheduled run if you want live Telegram delivery.

The batch file runs:

```powershell
python main.py --send-telegram
```

## Logging And Safety

- Logs are written to `data/logs/ai_trading_firm.log`.
- Telegram failures are logged and stored in SQLite.
- Market data snapshots are stored in SQLite.
- Score snapshots are stored in SQLite.
- Paper trading records are simulated-only and stored locally in SQLite.
- Paper review exports are written locally to `data/exports`.
- Paper journal notes are stored locally in SQLite for review only.
- The app never prints Telegram secrets.
- `risk.execution_enabled` must remain `false`.
- This repository is still research/reporting only.
- Real execution stays disabled even when market data or paper trading is available.

## Tests

If `pytest` is installed:

```powershell
pytest
```

The included tests do not require Telegram credentials.
