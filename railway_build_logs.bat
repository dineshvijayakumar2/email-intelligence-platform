@echo off
setlocal enabledelayedexpansion
title Railway - Build Logs

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
echo Fetching last 100 build log lines...
echo.
railway logs -b --lines 100
echo.
pause
endlocal
