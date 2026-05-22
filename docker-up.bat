@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0docker-up.ps1" %*
