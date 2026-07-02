@echo off
REM BMS Lot Tracking System - Quick Start Launcher
REM This batch file launches the enhanced lot tracking system

echo ============================================================
echo BMS LOT TRACKING SYSTEM
echo Enhanced Version with Real-time Tracking
echo ============================================================
echo.

REM Change to the script directory
cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.7 or later
    echo.
    pause
    exit /b 1
)

echo Starting system...
echo.

REM Launch the system
python launch_system.py

REM If there was an error
if errorlevel 1 (
    echo.
    echo ============================================================
    echo ERROR: System failed to start
    echo Check the error messages above
    echo ============================================================
    echo.
    pause
)

exit /b 0
