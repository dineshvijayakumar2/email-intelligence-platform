@echo off
setlocal enabledelayedexpansion
title Railway - Live Logs

echo [*] Checking login...
set WHOAMI_OUTPUT=
for /f "tokens=4 delims= " %%i in ('railway whoami 2^>^&1') do set WHOAMI_OUTPUT=%%i
echo !WHOAMI_OUTPUT! | findstr "@" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo [OK] Logged in as: !WHOAMI_OUTPUT!
) else (
    railway login
)
echo.
echo Streaming live logs... (Ctrl+C to stop)
echo.
railway logs
echo.
pause
endlocal
