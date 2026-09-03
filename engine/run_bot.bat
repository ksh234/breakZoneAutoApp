@echo off
chcp 65001 >nul
title breakZone bot (home PC)
rem -------------------------------------------------------------
rem  Bot launcher for home PC. Keep this window open during market hours.
rem  - Stop safely with Ctrl+C in this window (releases the lock).
rem  - Outside market hours the bot idles (heartbeat only, no orders).
rem  - Start/stop trading from the app (control screen). This window is for logs.
rem  - Log file: engine\logs\bot.log (rotating, also used by the server).
rem -------------------------------------------------------------
set ENGINE=D:\myWorkspace\breakZoneAutoApp\engine
set PY=%ENGINE%\.venv\Scripts\python.exe
set PYTHONIOENCODING=utf-8

if not exist "%PY%" (
  echo [ERROR] venv not found: %PY%
  pause
  exit /b 1
)
if not exist "%ENGINE%\.env" (
  echo [ERROR] %ENGINE%\.env not found. Fill Kiwoom/Supabase keys first.
  pause
  exit /b 1
)

cd /d "%ENGINE%"
echo ============================================================
echo  breakZone bot starting  %date% %time%
echo  Stop: Ctrl+C in this window   Log: %ENGINE%\logs\bot.log
echo ============================================================
"%PY%" -u -m src.main

echo.
echo ============================================================
echo  bot exited (%date% %time%). You can close this window.
echo ============================================================
pause
