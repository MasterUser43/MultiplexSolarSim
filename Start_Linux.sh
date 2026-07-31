#!/usr/bin/env bash

# First run:  installs everything into a local .venv, checks USB/serial
#             perms (one-time sudo prompts), then launches.
# Every run after: sees .venv already exists, skips straight to launch.
#
# Usage:
#   bash Start_Linux.sh            - normal launch, log panel + terminal output
#   bash Start_Linux.sh --no-log   - skip writing to logs/, terminal output only
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"

VENV_DIR=".venv"
APP_DIR=".app_internal"
REQ_FILE="$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/main.py" ]; then
    echo "[ERROR] $APP_DIR/main.py not found."
    echo "This launcher must stay in the same folder as the $APP_DIR folder."
    exit 1
fi

install() {
    echo "===================================================="
    echo "Multiplex Solar Simulator - First-Time Setup"
    echo "===================================================="
    echo "This only happens once. Please wait..."
    echo ""

    # --- Python check ---
    PYEXE=""
    if command -v python3 &>/dev/null; then
        PYEXE="python3"
    elif command -v python &>/dev/null; then
        PYEXE="python"
    fi
    if [ -z "$PYEXE" ]; then
        echo "[ERROR] No Python interpreter found (tried 'python3' and 'python')."
        echo "Install Python 3.10+ and re-run."
        exit 1
    fi
    PY_VERSION=$("$PYEXE" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    echo "[INFO] Using interpreter: $PYEXE (Python $PY_VERSION)"

    # --- venv module check ---
    if ! "$PYEXE" -c "import venv" &>/dev/null; then
        echo "[ERROR] The 'venv' module is not available for $PYEXE."
        echo "On Debian/Ubuntu, install it with:"
        echo "    sudo apt install python3-venv"
        echo "Then re-run this script."
        exit 1
    fi

    # --- Virtual environment ---
    if [ ! -d "$VENV_DIR" ]; then
        echo "[INFO] Creating local virtual environment..."
        "$PYEXE" -m venv "$VENV_DIR"
    fi
    if [ ! -f "$VENV_DIR/bin/activate" ]; then
        echo "[ERROR] Virtual environment creation failed ($VENV_DIR/bin/activate not found)."
        echo "Try running this command manually to see the actual error:"
        echo "    $PYEXE -m venv $VENV_DIR"
        exit 1
    fi

    source "$VENV_DIR/bin/activate"

    # --- Python packages ---
    echo "[INFO] Installing Python dependencies. This may take a few minutes..."
    pip install --upgrade pip -q
    if ! pip install -r "$REQ_FILE" -q; then
        echo "[ERROR] Failed to install Python dependencies from $REQ_FILE."
        exit 1
    fi

    # --- Hardware access check (one-time, interactive) ---
    echo ""
    echo "=== Hardware Backend Check ==="
    CURRENT_USER="$(id -un)"

    IN_DIALOUT=0
    if groups "$CURRENT_USER" | grep -qw dialout; then
        IN_DIALOUT=1
    fi
    if [ "$IN_DIALOUT" -eq 1 ]; then
        echo "[INFO] '$CURRENT_USER' is in the 'dialout' group -- relay serial access OK."
    else
        echo "[INFO] '$CURRENT_USER' is NOT in the 'dialout' group."
        echo "       Without this, the Numato relay will fail with a permission error."
        read -p "Add '$CURRENT_USER' to the 'dialout' group now? (requires sudo, one-time) (y/n): " add_dialout
        if [[ "$add_dialout" =~ ^[Yy]$ ]]; then
            sudo usermod -aG dialout "$CURRENT_USER"
            echo "[INFO] Added. Log out and back in (or run 'newgrp dialout') for it to take effect."
        else
            echo "[INFO] Skipped. See DEPLOYMENT.md to do this manually later."
        fi
    fi

    echo ""
    LIBUSB_FOUND=0
    if ldconfig -p 2>/dev/null | grep -q "libusb-1.0.so"; then
        LIBUSB_FOUND=1
    elif [ -f "/usr/lib/x86_64-linux-gnu/libusb-1.0.so.0" ] || [ -f "/usr/local/lib/libusb-1.0.so" ]; then
        LIBUSB_FOUND=1
    fi
    if [ "$LIBUSB_FOUND" -eq 1 ]; then
        echo "[INFO] libusb-1.0 found -- Keithley USB access via pyvisa-py should work."
    else
        echo "[INFO] libusb-1.0 was not found in standard system locations."
        read -p "Install libusb-1.0-0 now via apt? (requires sudo) (y/n): " install_libusb
        if [[ "$install_libusb" =~ ^[Yy]$ ]]; then
            sudo apt install -y libusb-1.0-0
        else
            echo "[INFO] Skipped. Install manually later with: sudo apt install libusb-1.0-0"
        fi
    fi

    UDEV_RULE_PATH="/etc/udev/rules.d/99-keithley.rules"
    echo ""
    if [ -f "$UDEV_RULE_PATH" ]; then
        echo "[INFO] Keithley udev rule already present at $UDEV_RULE_PATH."
    else
        echo "[INFO] No udev rule found for the Keithley 2460."
        read -p "Create the udev rule now? (requires sudo, one-time) (y/n): " add_udev
        if [[ "$add_udev" =~ ^[Yy]$ ]]; then
            echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="05e6", ATTRS{idProduct}=="2460", MODE="0666"' \
                | sudo tee "$UDEV_RULE_PATH" >/dev/null
            sudo udevadm control --reload-rules
            sudo udevadm trigger
            echo "[INFO] Rule installed. Unplug and replug the Keithley's USB cable."
        else
            echo "[INFO] Skipped. See DEPLOYMENT.md to do this manually later."
        fi
    fi

    mkdir -p logs

    echo ""
    echo "===================================================="
    echo "[SUCCESS] Installation complete. Launching the app now..."
    echo "===================================================="
}

# ========================================================================
#  HEALTH CHECK -- only install if the venv is missing
# ========================================================================
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    install
else
    echo "[INFO] Environment already set up -- skipping install."
    source "$VENV_DIR/bin/activate"
fi

# ========================================================================
#  LAUNCH
# ========================================================================
PYEXE=""
if command -v python3 &>/dev/null; then
    PYEXE="python3"
elif command -v python &>/dev/null; then
    PYEXE="python"
fi
if [ -z "$PYEXE" ]; then
    echo "[ERROR] Python not found in the virtual environment."
    echo "Delete the $VENV_DIR folder and re-run this script."
    exit 1
fi

echo "[INFO] Launching Multiplex Solar Simulator..."

pushd "$APP_DIR" >/dev/null

if [ "$1" = "--no-log" ]; then
    shift
    "$PYEXE" -u main.py "$@"
else
    mkdir -p ../logs
    LOGFILE="../logs/run_$(date +%Y%m%d_%H%M%S).log"
    echo "[INFO] Logging this session to logs/$(basename "$LOGFILE")"
    "$PYEXE" -u main.py "$@" 2>&1 | tee "$LOGFILE"
fi

popd >/dev/null
