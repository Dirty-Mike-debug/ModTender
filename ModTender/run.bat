@echo off
rem ModTender launcher: sets up a private Python environment the first time, then starts the app.
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

if not exist ".venv\Scripts\python.exe" (
    echo First run: setting up ModTender. This takes a minute...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo.
        echo Couldn't create the Python environment. Install Python 3.10 or newer from python.org
        echo and tick "Add python.exe to PATH" during setup, then run this again.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Installing PySide6 failed. Check your internet connection and try again.
        pause
        exit /b 1
    )
)

start "" ".venv\Scripts\pythonw.exe" main.py
