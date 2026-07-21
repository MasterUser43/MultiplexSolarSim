@echo off
REM run.bat
REM Start the Multiplex Solar Simulator.

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Please run install.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

REM --- Resolve a working Python interpreter inside the venv ---
set "PYEXE="
where python >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE (
    echo [ERROR] Python not found in the virtual environment. 
    echo Please delete the .venv folder and re-run install.bat.
    pause
    exit /b 1
)

echo [INFO] Launching Multiplex Solar Simulator...

REM Redirect its crash output to a log file
if not exist "logs" mkdir "logs"
set "LOGFILE=logs\run_latest.log"

REM Use 'python' instead of 'pythonw' below if you want a live console
REM window instead of (or in addition to) the log file.
start "" /B pythonw main.py %* > "%LOGFILE%" 2>&1

echo [INFO] Launched, please be patient. This window will close automatically...
timeout /t 2 /nobreak >nul

exit /b 0
