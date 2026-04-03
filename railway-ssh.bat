@echo off
setlocal enabledelayedexpansion

title Railway SSH Session

echo ============================================
echo        Railway SSH Connect Tool
echo ============================================
echo.

REM Step 1: Check if Railway CLI is installed
where railway >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Railway CLI not found. Installing now...
    cmd /c npm install -g @railway/cli
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to install Railway CLI. Make sure Node.js is installed.
        pause
        exit /b 1
    )
    echo [OK] Railway CLI installed.
    echo.
)

REM Step 2: Check login
echo [*] Checking login status...
set WHOAMI_OUTPUT=
for /f "tokens=4 delims= " %%i in ('railway whoami 2^>^&1') do set WHOAMI_OUTPUT=%%i

echo !WHOAMI_OUTPUT! | findstr "@" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo [OK] Logged in as: !WHOAMI_OUTPUT!
    echo.
) else (
    echo [*] Not logged in...
    cmd /c railway login
    echo [OK] Login done.
    echo.
)

REM Step 3: Menu - no railway link, all commands run in a fresh cmd window
:menu
echo.
echo ============================================
echo  What would you like to do?
echo   [1] SSH into backend service
echo   [2] Tail live logs
echo   [3] Filter error logs
echo   [4] Exit
echo ============================================
echo.
set ACTION=
set /p ACTION="Enter choice (1-4): "
echo.

if "!ACTION!"=="1" (
    start "Railway SSH" cmd /k "railway ssh"
    goto :menu
)

if "!ACTION!"=="2" (
    start "Railway Logs" cmd /k "railway logs --lines 100 || railway logs"
    goto :menu
)

if "!ACTION!"=="3" (
    start "Railway Error Logs" cmd /k "railway logs 2>&1 | findstr /i "error warn fail exception fatal""
    goto :menu
)

if "!ACTION!"=="4" (
    echo [*] Goodbye.
    exit /b 0
)

echo Invalid choice, try again.
goto :menu

endlocal