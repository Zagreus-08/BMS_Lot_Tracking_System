@echo off
echo Starting Label Printer...
echo.
cd /d "%~dp0"
.venv\Scripts\python.exe test.py
pause
