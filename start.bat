@echo off
title Blacknode
echo.
echo  ██████╗ ██╗      █████╗  ██████╗██╗  ██╗███╗   ██╗ ██████╗ ██████╗ ███████╗
echo  ██╔══██╗██║     ██╔══██╗██╔════╝██║ ██╔╝████╗  ██║██╔═══██╗██╔══██╗██╔════╝
echo  ██████╔╝██║     ███████║██║     █████╔╝ ██╔██╗ ██║██║   ██║██║  ██║█████╗
echo  ██╔══██╗██║     ██╔══██║██║     ██╔═██╗ ██║╚██╗██║██║   ██║██║  ██║██╔══╝
echo  ██████╔╝███████╗██║  ██║╚██████╗██║  ██╗██║ ╚████║╚██████╔╝██████╔╝███████╗
echo  ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═════╝ ╚══════╝
echo.

:: ── Python backend ────────────────────────────────────────────────────────────
echo  [1/2] Starting Python server  (http://127.0.0.1:7777)
start "Blacknode  |  Python Server" cmd /k "cd /d "%~dp0editor-server" && python server.py"

:: Give the server a moment to bind before the browser hits it
timeout /t 3 /nobreak > nul

:: ── Vite frontend ─────────────────────────────────────────────────────────────
echo  [2/2] Starting visual editor   (http://localhost:3000)
start "Blacknode  |  Editor (Vite)" cmd /k "cd /d "%~dp0editor" && npm run dev"

:: Open browser after Vite has had time to compile
timeout /t 5 /nobreak > nul
echo.
echo  Opening browser...
start http://localhost:3000
echo.
echo  Both processes are running in separate windows.
echo  Close those windows to stop the servers.
echo.
pause
