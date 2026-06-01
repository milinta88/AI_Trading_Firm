@echo off
REM Runs the AI Trading Firm daily brief in Telegram send mode.
REM Use this file with Windows Task Scheduler for a daily Phase 1 research report.
REM This project does not execute trades or place orders.

setlocal
pushd "%~dp0"
python main.py --send-telegram
set EXIT_CODE=%ERRORLEVEL%
popd
exit /b %EXIT_CODE%

