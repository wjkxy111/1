@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py %*
    exit /b !errorlevel!
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3 main.py %*
    exit /b !errorlevel!
)

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3 was not found. Install Python 3.11-3.13 first.
    exit /b 1
)

python main.py %*
exit /b !errorlevel!
