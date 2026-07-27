# Multiplex Solar Simulator Beta V1.0

**[Overview](README.md)** | **[Setup & Deployment Guide](DEPLOYMENT.md)** | **[Troubleshooting](DEPLOYMENT.md#troubleshooting-checklist)**
___

Python/PyQt5 GUI for automated multi-pixel solar cell IV characterization. Integrates a **Keithley 2460 SMU** and a **Numato 16-channel USB relay** for multiplexed testing.

## Hardware Requirements
1. **Keithley 2460 SourceMeter** (Connected via USB or Ethernet).
2. **Numato 16-Channel USB Relay Board**.
3. **Python 3.10+** (Ensure "Add to PATH" is checked during Windows install).

---

## Installation & Running

There is only **one file** you need to click w.r.t. operating system.

### Windows
Double-click **`Start_Windows.bat`**. 
- **First launch:** a terminal window opens and installs everything into a local, self-contained environment. Depending on internet connection and hardware specs, this should take ~5 minutes at worst.
- **Sequential launches:** the double-click launches the app directly, a splash screen pops up for slower hardware.

### Linux
Run:
```bash
bash Start_Linux.sh
```
- **First launch:** Installs the environment and walks you through the one-time USB/serial permission prompts (each needs `sudo` once).
- **Sequential launches:** launches directly.

Nothing is installed system-wide and is contained within a local `.venv`.

---

## What's in this folder

```
MultiplexSolarSim/
├── Start_Windows.bat     <- Double-click this on Windows
├── Start_Linux.sh        <- Run this on Linux
├── README.md
├── DEPLOYMENT.md
└── .app_internal/        <- Application source code
```

`.app_internal/` is hidden on purpose s.t. the application's internals may remain clean/untouched for the end-user. The launcher scripts are the only supported entry point.

When you launch the app, a splash screen appears immediately while the heavier numerical libraries finish loading in the background.

---

This project uses a **Self-Contained Hardware Backend**. If the system-wide NI-VISA driver is missing, the app automatically falls back to a portable Python-based driver (`pyvisa-py`).

## Documentation & Support
*   **Need help with permissions or COM ports?** See the **[Deployment Guide](DEPLOYMENT.md)**.
*   **Something not connecting?** Check the **[Troubleshooting Checklist](DEPLOYMENT.md#troubleshooting-checklist)**.
