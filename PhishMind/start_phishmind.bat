@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0backend"

if not exist ".venv\Scripts\pythonw.exe" (
    echo [PhishMind] No virtual environment found in backend\.venv
    echo.
    echo Run setup first, from the backend folder:
    echo     python -m venv .venv
    echo     .venv\Scripts\activate
    echo     pip install -r requirements.txt
    exit /b 1
)

if not exist ".env" (
    echo [PhishMind] backend\.env not found.
    echo Copy .env.example to .env and fill in your GEMINI_API_KEY
    echo ^(and IMAP_HOST / IMAP_USERNAME / IMAP_APP_PASSWORD to auto-watch your inbox^).
    exit /b 1
)

REM Belt-and-suspenders check: don't just trust phishmind.pid. If a previous
REM start was interrupted (e.g. Ctrl+C) before it could save its PID, the
REM server can still be alive and bound to port 8000 with nothing tracking
REM it. Check the port directly and clear out anything already listening
REM there before launching a new instance, so restarts never pile up orphans.
set FOUNDOLD=0
for /f "tokens=5" %%P in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":8000 "') do (
    if not "%%P"=="" (
        set FOUNDOLD=1
        echo [PhishMind] Found an existing process already on port 8000 ^(PID %%P^) - stopping it first...
        taskkill /F /PID %%P >nul 2>&1
    )
)
if exist "phishmind.pid" del phishmind.pid
if "!FOUNDOLD!"=="1" timeout /t 1 /nobreak >nul

echo [PhishMind] Starting in the background...

REM Launched directly via the native "start /B" instead of PowerShell's
REM Start-Process. That combination (Start-Process + file-redirected
REM stdout/stderr, captured through a "for /f" backtick) has been seen
REM hanging this script indefinitely on this machine, even though the
REM server itself started up and ran correctly underneath every time --
REM which pointed squarely at the PowerShell wrapper itself, not at
REM PhishMind. "start /B" has none of that redirection-capture behavior,
REM so it can't hang here the same way.
start "" /B ".venv\Scripts\pythonw.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000 > phishmind_out.log 2> phishmind_err.log

REM pythonw.exe needs a moment to import everything and bind the port, so
REM poll for it instead of assuming a PID -- this reuses the exact
REM netstat-based detection already proven reliable above and in
REM stop_phishmind.bat.
set BOUND=0
set PMPID=
for /l %%i in (1,1,20) do (
    if "!BOUND!"=="0" (
        for /f "tokens=5" %%P in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":8000 "') do (
            if not "%%P"=="" (
                set BOUND=1
                set PMPID=%%P
            )
        )
        if "!BOUND!"=="0" timeout /t 1 /nobreak >nul
    )
)

if "!BOUND!"=="0" (
    echo [PhishMind] Failed to start within 20 seconds. Check backend\phishmind_err.log for details.
    exit /b 1
)

echo !PMPID!> phishmind.pid

echo [PhishMind] Running silently in the background ^(PID !PMPID!^).
echo [PhishMind] It will keep scanning your inbox even with this window closed.
echo [PhishMind] Logs: backend\phishmind_out.log and backend\phishmind_err.log
echo [PhishMind] Dashboard: run "npm run dev" in the frontend folder, then open the URL it prints.
echo [PhishMind] To stop it: run stop_phishmind.bat
endlocal
