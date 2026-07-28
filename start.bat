@echo off
setlocal
title Blacknode

set "BLACKNODE_FORCE_RESTART=1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
set "BLACKNODE_EXIT=%errorlevel%"

if not "%BLACKNODE_EXIT%"=="0" (
    echo.
    echo  Blacknode launcher exited with code %BLACKNODE_EXIT%.
    echo  Check .local-logs for backend and editor logs.
    echo.
    pause
)

exit /b %BLACKNODE_EXIT%
