@echo off
setlocal
REM Registers a Windows scheduled task so PhishMind starts automatically,
REM silently, every time you log in - so it's always watching your inbox
REM without you having to remember to run start_phishmind.bat.

set TASKNAME=PhishMindBackground
set SCRIPT=%~dp0start_phishmind.bat

schtasks /Query /TN "%TASKNAME%" >nul 2>&1
if not errorlevel 1 (
    echo [PhishMind] Autostart task already exists. Removing old one first...
    schtasks /Delete /TN "%TASKNAME%" /F >nul 2>&1
)

schtasks /Create /TN "%TASKNAME%" /TR "\"%SCRIPT%\"" /SC ONLOGON /RL LIMITED /F
if errorlevel 1 (
    echo [PhishMind] Failed to create the scheduled task. Try running this as Administrator.
    exit /b 1
)

echo [PhishMind] Autostart enabled: PhishMind will start silently every time you log in.
echo [PhishMind] To undo this, run uninstall_autostart.bat
endlocal
