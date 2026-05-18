@echo off
title Blacknode

:: Banner (PowerShell script handles Unicode natively)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0banner.ps1"

:: Python deps
echo  Checking Python dependencies...
pip install -r "%~dp0editor-server\requirements.txt" -q --disable-pip-version-check
echo  Done.
echo.

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
