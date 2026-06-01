@echo off
REM AI Trading Firm Phase 1.6 dashboard launcher.
REM This starts the read-only Streamlit monitoring dashboard.
REM The dashboard does not execute trades, route orders, or connect to MT5.

cd /d "%~dp0"
streamlit run dashboard/app.py
