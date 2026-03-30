@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================
echo   Email Intelligence Platform (PROD DB)
echo ============================================
echo.
echo   WARNING: Backend will connect to PRODUCTION database
echo   Sync services will be auto-disabled
echo.

REM Check if we're in the right directory
if not exist "frontend" (
    echo ERROR: frontend directory not found
    goto :error
)
if not exist "backend" (
    echo ERROR: backend directory not found
    goto :error
)

REM Kill existing processes
echo Cleaning up existing processes...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM python3.13.exe >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo Previous processes cleaned up
echo.

REM ── Set USE_PROD_DB globally so child processes inherit it ──
set USE_PROD_DB=true

REM Start Backend with USE_PROD_DB
echo ========================================
echo   Starting Backend API Server (PROD DB)
echo ========================================
cd backend
call venv\Scripts\activate.bat
echo.
echo Backend API will start at http://localhost:8000
echo.
set BACKEND_DIR=%CD%

REM USE_PROD_DB is already in env — child cmd inherits it automatically
start "Backend API (PROD DB)" cmd /k "cd /d %BACKEND_DIR% && call venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

echo Waiting for backend to start...
timeout /t 5 /nobreak >nul
cd ..

REM Start Frontend
echo.
echo ========================================
echo   Starting Frontend Development Server
echo ========================================
cd frontend
set FRONTEND_DIR=%CD%
start "Frontend Dev Server (PROD DB)" cmd /k "cd /d %FRONTEND_DIR% && npm run dev:proddb"
echo Waiting for frontend to start...
timeout /t 5 /nobreak >nul
cd ..

echo.
echo ============================================
echo   Platform running with PRODUCTION DATABASE
echo ============================================
echo.
echo   Frontend:     http://localhost:3000
echo   Backend API:  http://localhost:8000 (PROD DB)
echo   API Docs:     http://localhost:8000/docs
echo.
echo   Sync services: DISABLED (no Gmail/Outlook polling)
echo   All other features work normally.
echo.

:loop
timeout /t 3600 /nobreak >nul
goto :loop

:error
echo.
echo Startup failed!
pause
exit /b 1

:end
endlocal
