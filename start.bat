@echo off
title Blacknode

:: Banner (PowerShell script handles Unicode natively)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0banner.ps1"

:: Python deps for the editor server
echo  Checking Python dependencies...
pip install -r "%~dp0editor-server\requirements.txt" -q --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo  ERROR: pip install failed. Fix the error above, then re-run start.bat.
    pause
    exit /b 1
)

:: Install the blacknode package itself so the `blacknode` CLI is available
:: (Claude Desktop's MCP config calls it by name). Only installs if missing.
pip show blacknode >nul 2>&1
if not errorlevel 1 goto :blacknode_installed
echo  Installing blacknode package for the CLI...
pushd "%~dp0"
pip install -e . -q --disable-pip-version-check
set "INSTALL_ERR=%errorlevel%"
popd
if not "%INSTALL_ERR%"=="0" (
    echo.
    echo  ERROR: could not install the blacknode package. Fix the error above and re-run.
    pause
    exit /b 1
)
:blacknode_installed

:: Install frontend deps on first run (or whenever node_modules is missing)
if not exist "%~dp0editor\node_modules" (
    echo  Installing frontend dependencies ^(first run, this can take a minute^)...
    pushd "%~dp0editor"
    call npm install
    popd
    if errorlevel 1 (
        echo.
        echo  ERROR: npm install failed. Make sure Node.js 20.19+ or 22.12+ is installed.
        pause
        exit /b 1
    )
)
echo  Done.
echo.

:: Free port 7777 if a previous server is still listening
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr " 127.0.0.1:7777 " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%p > nul 2>&1
)

:: Python backend
echo  [1/2] Starting Python server  (http://127.0.0.1:7777)
start "Blacknode | Python Server" cmd /k "cd /d "%~dp0editor-server" && python server.py"

timeout /t 3 /nobreak > nul

:: Vite frontend
echo  [2/2] Starting visual editor  (http://localhost:3000)
start "Blacknode | Editor (Vite)" cmd /k "cd /d "%~dp0editor" && npm run dev"

timeout /t 5 /nobreak > nul
echo.
echo  Opening browser...
start http://localhost:3000
echo.
echo  Both processes are running in separate windows.
echo  Close those windows to stop the servers.
echo.
pause
