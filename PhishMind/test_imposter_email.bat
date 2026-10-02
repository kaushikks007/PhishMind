@echo off
setlocal enabledelayedexpansion
REM One-command demo: feeds a fake "imposter brand" phishing email straight
REM into your running PhishMind backend via the API - no need to actually
REM send a real email and wait for the IMAP listener to pick it up.
REM
REM Usage:
REM   test_imposter_email.bat                -> uses backend\tests\samples\imposter_microsoft.eml
REM   test_imposter_email.bat path\to\some.eml -> uses that file instead

set SAMPLE=%~1
if "%SAMPLE%"=="" set SAMPLE=%~dp0backend\tests\samples\imposter_microsoft.eml

if not exist "%SAMPLE%" (
    echo [PhishMind] Could not find "%SAMPLE%"
    exit /b 1
)

echo [PhishMind] Sending "%SAMPLE%" to http://localhost:8000/api/v1/scan ...
echo.

powershell -NoProfile -Command ^
    "$raw = Get-Content -Raw -Path '%SAMPLE%'; " ^
    "try { " ^
    "  $body = @{ raw_email_text = $raw } | ConvertTo-Json; " ^
    "  $r = Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/scan' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 60; " ^
    "  $d = $r.data; " ^
    "  Write-Host ('Subject:      ' + $d.subject); " ^
    "  Write-Host ('Sender:       ' + $d.sender); " ^
    "  Write-Host ('Claimed brand:' + ' ' + $d.claimed_brand); " ^
    "  Write-Host ('Brand verified: ' + $d.is_brand_verified); " ^
    "  Write-Host ''; " ^
    "  Write-Host ('VERDICT: ' + $d.verdict + '   SCORE: ' + $d.risk_score + '/100') -ForegroundColor $(if ($d.verdict -eq 'PHISHING') {'Red'} elseif ($d.verdict -eq 'SUSPICIOUS') {'Yellow'} else {'Green'}); " ^
    "  Write-Host ''; " ^
    "  Write-Host 'Breakdown:'; " ^
    "  Write-Host ('  Technical:          ' + $d.breakdown.technical + '/25'); " ^
    "  Write-Host ('  Intent:             ' + $d.breakdown.intent + '/30'); " ^
    "  Write-Host ('  Social Engineering: ' + $d.breakdown.social_engineering + '/30'); " ^
    "  Write-Host ('  URL Signals:        ' + $d.breakdown.urls + '/15'); " ^
    "  Write-Host ('  Semantic Support:   ' + $d.breakdown.semantic_support + '/10'); " ^
    "  Write-Host ''; " ^
    "  Write-Host 'Evidence:'; " ^
    "  foreach ($e in $d.suspicious_evidence) { Write-Host ('  - ' + $e) }; " ^
    "  Write-Host ''; " ^
    "  Write-Host ('Explanation: ' + $d.explanation); " ^
    "} catch { " ^
    "  Write-Host 'Request failed - is PhishMind running? (start_phishmind.bat, then status_phishmind.bat to confirm)'; " ^
    "  Write-Host $_.Exception.Message " ^
    "}"

endlocal
