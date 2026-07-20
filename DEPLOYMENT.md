# Deployment Guide

One-time setup notes for running the Multiplex Solar Simulator on a new
machine. Most of this is handled automatically by `install.bat` /
`install.sh`.

This document exists for the steps that need a human decision (IT permissions, 
physical port identification) and as a reference if you skipped a prompt during 
install and need to do it later.

---

## Windows

### Installation
```
install.bat
```
Creates a local `.venv` folder inside the project directory and installs
everything from `requirements.txt` into it. 
Nothing is installed system-wide, and no administrator prompt should appear.

If your machine doesn't already have Python 3.10+, install it from
[python.org](https://www.python.org/downloads/) - during setup, check
**"Add python.exe to PATH"**. 

Typically, python is allowed through relevant IT-managed devices.

### "Windows protected your PC" / script execution warnings
Downloaded `.bat` files may trigger a SmartScreen warning on first run:
1. Click **"More info"**
2. Click **"Run anyway"**

This only appears once per file.

### Identifying the Numato Relay's COM port
The app auto-detects the relay by USB vendor/product ID, so this is only
needed for troubleshooting (e.g. confirming the OS sees the board at all):
1. Open **Device Manager** (Win+X → Device Manager)
2. Expand **Ports (COM & LPT)**
3. Plug the relay in - a new entry should appear, e.g.
   `USB Serial Device (COM5)`
4. If it instead shows under **Other devices** with a yellow warning icon,
   the driver isn't installed - see the
   [Numato driver downloads](https://numato.com/product/16-channel-usb-relay-module#downloads)
   linked in the main README.

### Identifying the Keithley 2460
`install.bat` checks for `visa32.dll` (NI-VISA) and reports whether it
found a system-wide install or will fall back to the bundled
`pyvisa-py` + `libusb-package` backend - either is fine

To confirm Windows itself sees the instrument regardless of
which backend is used:
1. Open **Device Manager**
2. Look under **Universal Serial Bus devices** (or **libusbK/WinUSB
   devices** if a VISA driver has claimed it) for an entry resembling
   `Keithley Instruments SMU 2460`

### Troubleshooting checklist
- App won't start, nothing visible happens → check `logs\run_latest.log`
- "Keithley not found" in the app's log panel, but Device Manager sees it
  → try deleting `.venv` and re-running `install.bat` to reinstall
  `pyvisa-py`/`pyusb`/`libusb-package` cleanly
- Relay not found → confirm its COM port appears in Device Manager per
  above; if not, it's a cabling/driver issue, not a software one

---

## Linux

### Installation
```bash
bash install.sh
```
Creates a local `.venv`, installs `requirements.txt`, and interactively
checks three things needed for hardware access through one-time
sudo fix or tells you to do it manually (documented below). Nothing is
run with sudo w/o an explicit y/n prompt first.

If `install.sh` reports the `venv` module is missing (common on
Debian/Ubuntu, where it's a separate package from `python3` itself):
```bash
sudo apt install python3-venv
```

### One-time hardware permission setup
These are the three checks `install.sh` runs automatically. Manual
versions below, if you skipped a prompt or are setting up a machine where
you don't have your own sudo access yet.

**1. Serial access for the Numato relay** - your user needs to be in the
`dialout` group:
```bash
sudo usermod -aG dialout $USER
```
Log out and back in (or run `newgrp dialout` in the current terminal) -
group membership changes don't apply to already-open sessions.

**2. libusb for the Keithley (pyvisa-py backend)** - the Keithley talks
over USBTMC via `pyvisa-py`, which needs the system `libusb-1.0` library.
```bash
sudo apt install libusb-1.0-0
```

**3. udev rule for the Keithley** - grants your user raw USB access to the
instrument specifically (the `dialout` group above only covers the
relay's serial port, not the Keithley's USB connection):
```bash
sudo nano /etc/udev/rules.d/99-keithley.rules
```
Add this line:
```
SUBSYSTEM=="usb", ATTRS{idVendor}=="05e6", ATTRS{idProduct}=="2460", MODE="0666"
```
Then:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```
Unplug and replug the Keithley's USB cable - the rule applies on the next
enumeration, not retroactively to an already-connected device.

### Verifying the OS sees both instruments
Useful before even opening the app:
```bash
lsusb
```
Look for a `05e6:2460` (Keithley) and a `2a19:0c03` (Numato) entry. If
either is missing, that's a cabling/power problem, not a permissions or
software one - check the physical connection before troubleshooting.

### Running
```bash
bash run.sh
```
Runs in the foreground with a visible terminal. Every run is
also logged to `logs/run_<timestamp>.log` for later review. Use
`bash run.sh --no-log` to skip writing the log file.

### Troubleshooting checklist
- "Relay not found" but `lsusb` shows it → almost always the `dialout`
  group step above; a permission error at the OS level surfaces through
  `find_numato()` as a generic "not found," not a permission message
- "Keithley not found" but `lsusb` shows it → check the udev rule (step 3)
  is actually in place, and that you replugged the cable after adding it
- Both instruments missing from `lsusb` entirely → hardware/cabling issue,
  not a setup issue - check physical connections and power before
  revisiting any of the above