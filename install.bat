@echo off
REM install.bat
REM Windows setup for the Multiplex Solar Simulator.
REM Run once from the repo root: install.bat

setlocal
cd /d "%~dp0"

echo ====================================================
echo Multiplex Solar Simulator - Installation
echo ====================================================

REM --- Python check ---
set "PYEXE="
python --version >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE (
    py -3 --version >nul 2>&1 && set "PYEXE=py -3"
)

if not defined PYEXE (
    echo [ERROR] No Python interpreter found.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Ensure "Add python.exe to PATH" is checked during installation.
    pause
    exit /b 1
)
echo [INFO] Using interpreter: %PYEXE%

REM --- Virtual environment ---
if not exist ".venv\" (
    echo [INFO] Creating local virtual environment...
    %PYEXE% -m venv .venv
)

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment creation failed.
    echo This can happen if your Python install is missing the 'venv' module,
    echo or if an antivirus/IT policy blocked writing to this folder.
    echo Try running this command manually to see the actual error:
    echo     %PYEXE% -m venv .venv
    pause
    exit /b 1
)

echo [INFO] Activating environment and installing packages...
call .venv\Scripts\activate.bat

REM --- Python packages ---
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Failed to install Python dependencies. 
    pause
    exit /b 1
)

REM --- Driver Check (Informational Only) ---
echo.
echo === Hardware Backend Check ===

set "NIVISA_FOUND=0"
if exist "C:\Windows\System32\visa32.dll" set "NIVISA_FOUND=1"
if exist "C:\Windows\SysWOW64\visa32.dll" set "NIVISA_FOUND=1"

if "%NIVISA_FOUND%"=="1" (
    echo [INFO] System-wide NI-VISA detected. 
    echo        Hardware communication will be prioritized through the native driver.
) else (
    echo [INFO] No system VISA detected. 
    echo        Hardware communication will use the self-contained 'pyvisa-py' backend.
    echo        (Note: If the Keithley is not detected, ensure it is in 'USB TMC' mode).
)

echo.
echo ====================================================
echo [SUCCESS] Installation complete.
echo To start the application, run: run.bat
echo ====================================================
pause