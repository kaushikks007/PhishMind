@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0backend"

set STOPPEDANY=0

if exist "phishmind.pid" (
    set /p PMPID=<phishmind.pid
    tasklist /FI "PID eq !PMPID!" 2>nul | find "!PMPID!" >nul
    if not errorlevel 1 (
        echo [PhishMind] Stopping PhishMind ^(PID !PMPID!^)...
        taskkill /PID !PMPID! /F >nul 2>&1
        set STOPPEDANY=1
    )
    del phishmind.pid
)

REM phishmind.pid can go stale (e.g. a previous start was interrupted with
REM Ctrl+C before it saved its PID, see start_phishmind.bat). Also check
REM port 8000 directly so "stop" actually stops whatever's running, even if
REM it was never tracked in the PID file.
for /f "tokens=5" %%P in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":8000 "') do (
    if not "%%P"=="" (
        echo [PhishMind] Stopping untracked process on port 8000 ^(PID %%P^)...
        taskkill /F /PID %%P >nul 2>&1
        set STOPPEDANY=1
    )
)

if "!STOPPEDANY!"=="0" (
    echo [PhishMind] Not running.
) else (
    echo [PhishMind] Stopped.
)
endlocal
