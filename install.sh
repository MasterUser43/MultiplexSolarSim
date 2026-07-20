#!/usr/bin/env bash
# install.sh
# Linux setup for the Multiplex Solar Simulator.
# Run once from the repo root: bash install.sh
set -e

echo "===================================================="
echo "Multiplex Solar Simulator - Installation"
echo "===================================================="

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
# On Debian/Ubuntu, python3-venv is a separate apt package and is often
# missing even when python3 itself is installed. Check for it
# so the failure message points at the actual fix
if ! "$PYEXE" -c "import venv" &>/dev/null; then
    echo "[ERROR] The 'venv' module is not available for $PYEXE."
    echo "On Debian/Ubuntu, install it with:"
    echo "    sudo apt install python3-venv"
    echo "Then re-run this script."
    exit 1
fi

# --- Virtual environment ---
if [ ! -d ".venv" ]; then
    echo "[INFO] Creating local virtual environment..."
    "$PYEXE" -m venv .venv
fi

if [ ! -f ".venv/bin/activate" ]; then
    echo "[ERROR] Virtual environment creation failed (.venv/bin/activate not found)."
    echo "Try running this command manually to see the actual error:"
    echo "    $PYEXE -m venv .venv"
    exit 1
fi

source .venv/bin/activate

# --- Python packages ---
echo "[INFO] Installing Python dependencies..."
pip install --upgrade pip -q
if ! pip install -r requirements.txt -q; then
    echo "[ERROR] Failed to install Python dependencies."
    exit 1
fi

# --- Hardware access check ---
echo ""
echo "=== Hardware Backend Check ==="

CURRENT_USER="$(id -un)"

# 1. Serial (Numato relay) -- needs the user in the 'dialout' group.
IN_DIALOUT=0
if groups "$CURRENT_USER" | grep -qw dialout; then
    IN_DIALOUT=1
fi

if [ "$IN_DIALOUT" -eq 1 ]; then
    echo "[INFO] '$CURRENT_USER' is in the 'dialout' group -- relay serial access OK."
else
    echo "[INFO] '$CURRENT_USER' is NOT in the 'dialout' group."
    echo "       Without this, the Numato relay will fail with a permission"
    echo "       error (not 'not found') when the app tries to open its port."
    read -p "Add '$CURRENT_USER' to the 'dialout' group now? (requires sudo, one-time) (y/n): " add_dialout
    if [[ "$add_dialout" =~ ^[Yy]$ ]]; then
        sudo usermod -aG dialout "$CURRENT_USER"
        echo "[INFO] Added. You must log out and back in (or run 'newgrp dialout'"
        echo "       in this terminal) before the new group membership takes effect."
    else
        echo "[INFO] Skipped. See DEPLOYMENT.md to do this manually later."
    fi
fi

# 2. USB (Keithley 2460 via pyvisa-py) -- needs libusb.
# Note: unlike on Windows, the 'libusb-package' pip package generally does
# NOT bundle a Linux binary
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
    echo "The Keithley 2460 talks over USBTMC via the 'pyvisa-py' backend,"
    echo "which needs the system libusb-1.0 library (separate from the pip package)."
    read -p "Install libusb-1.0-0 now via apt? (requires sudo) (y/n): " install_libusb
    if [[ "$install_libusb" =~ ^[Yy]$ ]]; then
        sudo apt install -y libusb-1.0-0
    else
        echo "[INFO] Skipped. Install manually later with: sudo apt install libusb-1.0-0"
    fi
fi

# 3. udev rule for the Keithley (raw USB device permissions).
# This is the USB equivalent of the dialout group fix above, but for the
# Keithley specifically -- dialout only covers serial (the relay).
UDEV_RULE_PATH="/etc/udev/rules.d/99-keithley.rules"
echo ""
if [ -f "$UDEV_RULE_PATH" ]; then
    echo "[INFO] Keithley udev rule already present at $UDEV_RULE_PATH."
else
    echo "[INFO] No udev rule found for the Keithley 2460."
    echo "       Without it, connecting may fail with a USB permission error"
    echo "       even though the device shows up in 'lsusb'."
    read -p "Create the udev rule now? (requires sudo, one-time) (y/n): " add_udev
    if [[ "$add_udev" =~ ^[Yy]$ ]]; then
        echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="05e6", ATTRS{idProduct}=="2460", MODE="0666"' \
            | sudo tee "$UDEV_RULE_PATH" >/dev/null
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        echo "[INFO] Rule installed. Unplug and replug the Keithley's USB cable"
        echo "       for it to take effect on the currently-attached device."
    else
        echo "[INFO] Skipped. See DEPLOYMENT.md to do this manually later."
    fi
fi

mkdir -p logs

echo ""
echo "===================================================="
echo "[SUCCESS] Installation complete."
echo "To start the application, run: bash run.sh"
echo "===================================================="
