@echo off
setlocal
cd /d "%~dp0backend"

if not exist "phishmind.pid" (
    echo [PhishMind] Not running.
    exit /b 0
)

set /p PMPID=<phishmind.pid
tasklist /FI "PID eq %PMPID%" 2>nul | find "%PMPID%" >nul
if errorlevel 1 (
    echo [PhishMind] phishmind.pid exists but process %PMPID% is not running.
    exit /b 1
)

echo [PhishMind] Process running ^(PID %PMPID%^). Checking API, watcher, and inbox listener...
powershell -NoProfile -Command ^
    "try { $h = Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/health' -TimeoutSec 5; " ^
    "$l = Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/listener/status' -TimeoutSec 5; " ^
    "$w = Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/watcher/status' -TimeoutSec 5; " ^
    "Write-Host ('API: ' + $h.status); " ^
    "if ($w.data.enabled) { " ^
    "  Write-Host ('Email-activity watcher: enabled'); " ^
    "  Write-Host ('Email window currently open: ' + $w.data.scanning_active); " ^
    "} else { " ^
    "  Write-Host ('Email-activity watcher: disabled (always-on mode, or no IMAP credentials set)'); " ^
    "}; " ^
    "Write-Host ('Inbox listener running: ' + $l.data.running); " ^
    "Write-Host ('Watching: ' + $l.data.username) } " ^
    "catch { Write-Host 'API did not respond on http://localhost:8000 (still starting up, or crashed - check phishmind_err.log)' }"
endlocal
