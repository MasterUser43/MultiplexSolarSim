@echo off
REM First run:  installs everything into a local .venv (visible progress
REM              in this terminal), then launches the app.
REM Every run after: sees .venv already exists, skips straight to launch.

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "APP_DIR=.app_internal"
set "REQ_FILE=%APP_DIR%\requirements.txt"

if not exist "%APP_DIR%\main.py" (
    echo [ERROR] %APP_DIR%\main.py not found.
    echo This launcher must stay in the same folder as the %APP_DIR% folder.
    pause
    exit /b 1
)

REM ====================================================================
REM  HEALTH CHECK -- only install if the venv is missing
REM ====================================================================
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    call :install
    if errorlevel 1 (
        pause
        exit /b 1
    )
) else (
    echo [INFO] Environment already set up -- skipping install.
)

REM ====================================================================
REM  LAUNCH
REM ====================================================================
call "%VENV_DIR%\Scripts\activate.bat"

if not exist "logs" mkdir "logs"
set "LOGFILE=%cd%\logs\run_latest.log"

echo [INFO] Launching Multiplex Solar Simulator...
pushd "%APP_DIR%"

REM pythonw = windowed Python, no console flash on every launch.
REM Crash output still goes to logs\run_latest.log for troubleshooting.
start "" /B pythonw main.py %* > "%LOGFILE%" 2>&1
popd

echo [INFO] Launched. The splash screen should appear in a moment.
echo        This window will close automatically...
timeout /t 2 /nobreak >nul
exit /b 0

REM ====================================================================
REM  :install -- first-run setup only
REM ====================================================================
:install
echo ====================================================
echo Multiplex Solar Simulator - First-Time Setup
echo ====================================================
echo This only happens once. Please wait...
echo.

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
    exit /b 1
)

REM --- Python Version Enforcement (3.10+) ---
%PYEXE% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo [ERROR] Python 3.10 or higher is required.
    echo Please upgrade your Python installation.
    exit /b 1
)
echo [INFO] Using interpreter: %PYEXE%

REM --- Virtual environment ---
if not exist "%VENV_DIR%\" (
    echo [INFO] Creating local virtual environment...
    %PYEXE% -m venv "%VENV_DIR%"
)
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [ERROR] Virtual environment creation failed.
    echo This can happen if your Python install is missing the 'venv' module,
    echo or if an antivirus/IT policy blocked writing to this folder.
    echo Try running this command manually to see the actual error:
    echo     %PYEXE% -m venv %VENV_DIR%
    exit /b 1
)

echo [INFO] Activating environment and installing packages...
call "%VENV_DIR%\Scripts\activate.bat"

echo [INFO] This may take a few minutes on first run while packages download.
echo.
python -m pip install --upgrade pip
python -m pip install -r "%REQ_FILE%"
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install Python dependencies. See the messages above for details.
    exit /b 1
)

REM --- Driver check (informational only) ---
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
echo Launching the app now...
echo ====================================================
echo.
exit /b 0
