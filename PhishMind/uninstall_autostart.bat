@echo off
setlocal
set TASKNAME=PhishMindBackground

schtasks /Query /TN "%TASKNAME%" >nul 2>&1
if errorlevel 1 (
    echo [PhishMind] Autostart was not enabled.
    exit /b 0
)

schtasks /Delete /TN "%TASKNAME%" /F >nul 2>&1
echo [PhishMind] Autostart disabled. Use start_phishmind.bat to run it manually.
endlocal
