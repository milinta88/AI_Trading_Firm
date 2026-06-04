# Sample Daily Brief

This sample shows the report structure. When the optional read-only `dxy_provider` and `gold_spot_provider` are still disabled, the Gold DXY and spot lines remain `NOT_CONFIGURED`.

```text
AI Trading Firm Daily Brief
Date: 2026-05-28
Mode: Research
Execution: Disabled (Research Only)

Market Data:
BTC Price: 72,733.07 USDT
Fear & Greed Index: 22 (Extreme Fear)
BTC Funding Rate: 0.0100%
BTC Open Interest: 106,924.062
Gold Macro Data Status:
US10Y: 4.47 (2026-05-14)
Real Yield: 2.16 (2026-05-22)
Fed Funds: 4.33 (2026-05-01)
CPI: 320.0 (2026-05-01)
DXY: NOT_CONFIGURED
Gold Spot Price: NOT_CONFIGURED

BTC Trend Context:
- Price: rising (+250.0000, +0.34%). BTC price is rising versus the previous persisted snapshot.
- Fear & Greed: flat (+0.0000, +0.00%). BTC Fear & Greed is flat versus the previous persisted snapshot.
- Funding Rate: flat (+0.0000, +0.00%). BTC funding rate is flat versus the previous persisted snapshot.
- Open Interest: flat (+0.0000, +0.00%). BTC open interest trend is flat or lacks price confirmation.

Gold Macro Trend Context:
- US10Y: falling (-0.0500, -1.11%). US10Y is falling versus the previous persisted snapshot, which is generally supportive for gold.
- Real Yield: falling (-0.0300, -1.37%). Real yield is falling versus the previous persisted snapshot, which is generally supportive for gold.
- Fed Funds: flat (+0.0000, +0.00%). Fed Funds trend is flat; it is tracked as macro context for now.
- CPI: INSUFFICIENT_HISTORY. CPI needs at least two persisted OK snapshots for trend analysis.

Gold:
Bias: Bullish
Total Score: 75/100
Confidence: Medium
Data Completeness: 67%
Key Reasons:
- US10Y is 4.47 and recently fell, which is supportive for gold.
- Real Yield is 2.16 and recently fell, which is supportive for gold.
- Fed Funds is 4.33 and is currently tracked as informational context.
Score Breakdown:
- DXY: +0/8 (NOT_CONFIGURED)
- US10Y: +10/10 (OK) value=4.47
- Real Yield: +15/15 (OK) value=2.16
- Fed Funds: +0/5 (OK) value=4.33
- CPI: +0/5 (OK) value=320.0
- Gold Spot Price: +0/5 (NOT_CONFIGURED)
Warnings:
- DXY live macro data is not configured yet.
- Gold spot price integration is not configured yet.

BTC:
Bias: Bearish
Total Score: 40/100
Confidence: High
Data Completeness: 100%
Key Reasons:
- Read-only BTCUSDT public price snapshot: 72,733.07 USDT.
- Fear & Greed is 22 (Extreme Fear), which signals risk-off sentiment.
- Funding rate is 0.0100%, which is close to neutral.
- BTC open interest trend is flat or lacks price confirmation.
Score Breakdown:
- BTC Price: +5/5 (OK)
- Fear & Greed: -15/15 (OK)
- Funding Rate: +0/10 (OK) value=0.0100%
- Open Interest: +0/5 (OK) value=106,924.062
Warnings:
- None

Market Regime And Data Readiness:
BTC:
- Regime: TREND_DOWN | Readiness Score: 100/100 | Decision Ready: YES
- Data Completeness: 100%
- Stale Sources: None
- Missing Sources: None
Gold:
- Regime: INSUFFICIENT_DATA | Readiness Score: 20/100 | Decision Ready: NO
- Data Completeness: 20%
- Stale Sources: Gold CPI, Gold Fed Funds
- Missing Sources: Gold DXY, Gold Spot Price
- No-Trade Readiness Reasons:
  - Gold regime classification requires at least 10 persisted OK US10Y and real-yield snapshots.
  - Stale sources: Gold CPI, Gold Fed Funds.
  - Missing sources: Gold DXY, Gold Spot Price.
  - Readiness score 20 is below the configured minimum 70.

Strategy Hypotheses:
BTC:
- Status: WATCH | Direction: SHORT | Family: BTC_SENTIMENT_MEAN_REVERSION
- Regime: TREND_DOWN | Readiness: 100/100 | Score: 40/100 | Confidence: High
- Holding Period: 1-3 days
  - Reason: Fear & Greed is deeply fearful at 22, so a contrarian long or short review must stay hypothesis-only and carefully monitored.
  - Blocker: Current BTC inputs still need later forward-testing before any paper-strategy promotion.
Gold:
- Status: BLOCKED | Direction: NO_TRADE | Family: GOLD_NO_TRADE
- Regime: INSUFFICIENT_DATA | Readiness: 20/100 | Score: 75/100 | Confidence: Medium
- Holding Period: Watchlist only
  - Blocker: Gold regime classification requires at least 10 persisted OK US10Y and real-yield snapshots.
  - Blocker: Missing sources: Gold DXY, Gold Spot Price.

Hypothesis Outcomes:
- BTC 24h: FAVORABLE | Direction: SHORT | Family: BTC_SENTIMENT_MEAN_REVERSION | Move: -1.40%
  - Reason: SHORT hypothesis saw a -1.40% underlying move by the evaluation horizon, which was favorable versus the neutral threshold of 0.25%.
- Gold 24h: BLOCKED_NOT_EVALUATED | Direction: NO_TRADE | Family: GOLD_NO_TRADE | Move: N/A
  - Reason: Hypothesis status is BLOCKED, so outcome tracking remains informational only.

Hypothesis Review Analytics:
- Evaluated: 12 | Favorable: 7 (58%) | Unfavorable: 3 (25%) | Neutral: 2 (17%)
- Insufficient Follow-Up: 4 | Blocked Not Evaluated: 2
  - Review Candidate: BTC_SENTIMENT_MEAN_REVERSION (BTC) fav=58% n=12
  - Candidate Progress: GOLD_MACRO_PRESSURE (Gold) NEED_MORE_SAMPLES n=4/10
  - Warning: Gold review sample size is still too small for any candidate flag.

Macro Regime:
Neutral

Data Quality:
Overall Status: WARNING
Source Statuses:
BTC Price: OK
BTC Fear And Greed Index: OK
BTC Funding Rate: OK
BTC Open Interest: OK
Gold Dxy: NOT_CONFIGURED
Gold Us10Y: OK
Gold Real Yield: OK
Gold Fed Funds: OK
Gold Cpi: OK
Gold Spot Price: NOT_CONFIGURED
Notes:
- Gold Dxy is not configured yet. DXY live macro data is not configured yet.
- Gold Spot Price is not configured yet. Gold spot price integration is not configured yet.

Risk Status:
Status: ELEVATED
Data Quality: WARNING
Trade Permission: WATCH ONLY
Daily Loss: 0.00%
Weekly Loss: 0.00%
Risk Notes:
- Phase 1 remains research-only; no real orders can be sent.
- Configured daily loss cap: 1.00%.
- Configured weekly loss cap: 3.00%.
- At least one asset has weak placeholder conviction below the research threshold.
- Low confidence detected for: Gold.
- Low data completeness detected for: Gold.

System Health:
SQLite: OK
BTC public data: OK
Fear & Greed: OK
BTC derivatives data: OK
FRED: OK
Gold macro data: WARNING
MT5: NOT_CONFIGURED
Exchange private API: NOT_CONFIGURED
Telegram: DRY_RUN
```
