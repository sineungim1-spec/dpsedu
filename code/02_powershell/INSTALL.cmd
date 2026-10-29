@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File 00_install_windows.ps1
pause
