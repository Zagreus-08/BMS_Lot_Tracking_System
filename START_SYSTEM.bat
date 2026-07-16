@echo off
REM BMS Lot Tracking System - Quick Start Launcher
REM Auto-detects WinPython portable installation

echo ============================================================
echo BMS LOT TRACKING SYSTEM
echo Enhanced Version with Real-time Tracking
echo ============================================================
echo.

REM Change to the script directory
cd /d "%~dp0"

REM Try to find portable Python (WinPython)
set PYTHON_EXE=
set SEARCH_DIRS=C:\Users\a493353\Downloads\WPy64-3771

echo Searching for WinPython portable installation...

REM Check common locations
for %%D in (%SEARCH_DIRS%) do (
    if exist "%%D\python-3.7.7.amd64\python.exe" (
        set PYTHON_EXE=%%D\python-3.7.7.amd64\python.exe
        echo Found WinPython: %%D\python-3.7.7.amd64\python.exe
        goto :found_python
    )
)

REM Check for any WPy* directory
for /d %%D in (WPy*) do (
    for /f "delims=" %%P in ('dir /s /b "%%D\python.exe" 2^>nul') do (
        set PYTHON_EXE=%%P
        echo Found WinPython: %%P
        goto :found_python
    )
)

REM Check parent directory for WPy* 
cd ..
for /d %%D in (WPy*) do (
    for /f "delims=" %%P in ('dir /s /b "%%D\python.exe" 2^>nul') do (
        set PYTHON_EXE=%%P
        echo Found WinPython: %%P
        cd "%~dp0"
        goto :found_python
    )
)
cd "%~dp0"

REM If not found, try system Python
echo WinPython not found in standard locations
echo Checking for system Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python not found!
    echo.
    echo Please ensure WinPython is in one of these locations:
    echo   - Same directory as this system
    echo   - Parent directory
    echo   - Named: WPy64-3771, WinPython, or Python
    echo.
    pause
    exit /b 1
) else (
    set PYTHON_EXE=python
    echo Using system Python
)

:found_python
echo.
echo Starting system with: %PYTHON_EXE%
echo.

REM Launch the system
"%PYTHON_EXE%" launch_system.py

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
