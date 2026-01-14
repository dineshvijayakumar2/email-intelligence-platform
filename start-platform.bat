@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================
echo   Email Intelligence Platform Startup (Windows)
echo ============================================
echo.

REM Check for environment parameter
set ENVIRONMENT=%1
if "%ENVIRONMENT%"=="" set ENVIRONMENT=development
echo Environment: %ENVIRONMENT%
echo.

REM Check if we're in the right directory
if not exist "frontend" (
    echo ERROR: frontend directory not found
    echo Please run this script from the Email Intelligence root directory
    echo.
    echo Expected structure:
    echo   Email Intelligence/
    echo   +-- frontend/
    echo   +-- backend/
    echo   +-- start-poc.bat
    goto :error
)

if not exist "backend" (
    echo ERROR: backend directory not found
    echo Please run this script from the Email Intelligence root directory
    goto :error
)

REM Kill existing processes to ensure clean start
echo Cleaning up existing processes...
echo.

REM Kill Python processes (backend)
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM python3.13.exe >nul 2>&1

REM Kill Node processes (frontend)
taskkill /F /IM node.exe >nul 2>&1

REM Wait a moment for processes to fully terminate
timeout /t 2 /nobreak >nul

echo Previous processes cleaned up
echo.

REM Start Backend
echo ========================================
echo   Starting Backend API Server...
echo ========================================
cd backend

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is required but not installed
    echo Please install Python 3.8+ and try again
    cd ..
    goto :error
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating Python virtual environment...
    python -m venv venv
)

REM Activate virtual environment and install dependencies
call venv\Scripts\activate.bat
echo Installing Python dependencies...
pip install -r requirements.txt >nul 2>&1

echo.
echo Backend API will start at http://localhost:8000
echo API docs will be available at http://localhost:8000/docs
echo.

REM Start the backend server in a new window
echo Starting backend in new window...
set BACKEND_DIR=%CD%
start "Backend API Server" cmd /k "cd /d "%BACKEND_DIR%" && venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

REM Wait for server to start
echo Waiting for backend to start...
timeout /t 5 /nobreak >nul

REM Check if backend started successfully
curl -s http://localhost:8000/api/emails/categories >nul 2>&1
if %errorlevel% equ 0 (
    echo Backend API is running
) else (
    echo WARNING: Backend API may not have started properly
    echo Check the Backend API Server window for details
)

cd ..

REM Start Frontend
echo.
echo ========================================
echo   Starting Frontend Development Server...
echo ========================================
cd frontend

REM Check if Node.js is available
npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js/npm is required but not installed
    echo Please install Node.js and try again
    cd ..
    goto :error
)

REM Install dependencies if node_modules doesn't exist
if not exist "node_modules" (
    echo Installing Node.js dependencies...
    npm install >nul 2>&1
)

echo.
echo Frontend will start at http://localhost:3000
echo.

REM Start the frontend server in a new window
echo Starting frontend in new window...
set FRONTEND_DIR=%CD%
start "Frontend Dev Server" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

REM Wait for server to start
echo Waiting for frontend to start...
timeout /t 5 /nobreak >nul

echo Frontend window opened
cd ..

REM Display startup summary
echo.
echo ============================================
echo   Email Intelligence Platform is now running!
echo ============================================
echo.
echo   Frontend:     http://localhost:3000
echo   Backend API:  http://localhost:8000
echo   API Docs:     http://localhost:8000/docs
echo.
echo   Service Windows:
echo     - Backend API Server (separate window)
echo     - Frontend Dev Server (separate window)
echo.
echo To test the Platform:
echo   1. Open http://localhost:3000 in your browser
echo   2. Navigate to Mailboxes -^> Add Mailbox
echo   3. Choose file source (Local File or Google Drive)
echo   4. For Google Drive: Connect -^> Authenticate -^> Select file
echo   5. Test connection and create mailbox
echo   6. Use 'Process' button to start email analysis
echo   7. Monitor progress on Dashboard
echo.
echo To stop all services:
echo   Close the Backend and Frontend windows
echo.
echo This window will stay open. Press Ctrl+C to exit.
echo.

REM Keep the window open
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
