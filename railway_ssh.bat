@echo off
setlocal enabledelayedexpansion
title Railway - SSH

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
echo [*] Connecting to SSH... (type 'exit' to quit)
echo.
railway ssh
echo.
echo [*] Session ended.
pause
endlocal
