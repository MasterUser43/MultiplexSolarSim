# Multiplex Solar Simulator - IV Characterization

**[Overview](README.md)** | **[Setup & Deployment Guide](DEPLOYMENT.md)** | **[Troubleshooting](DEPLOYMENT.md#troubleshooting-checklist)**
___

Python/PyQt5 GUI for automated multi-pixel solar cell IV characterization. Integrates a **Keithley 2460 SMU** and a **Numato 16-channel USB relay** for multiplexed testing.

## Hardware Requirements
1. **Keithley 2460 SourceMeter** (Connected via USB or Ethernet).
2. **Numato 16-Channel USB Relay Board**.
3. **Python 3.10+** (Ensure "Add to PATH" is checked during Windows install).

---

## Installation

The Multiplex Solar Simulator features a **Zero-Config** installation process. It is designed to run in IT-managed lab environments where administrative privileges are restricted.

### Windows (Primary)
1. Ensure Python 3.10+ is installed.
2. Double-click **`install.bat`**. This creates a local virtual environment and sets up portable drivers inside the project folder.
3. Run the application with **`run.bat`**.

### Linux
1. Run `bash install.sh` in your terminal. 
2. Follow the interactive prompts to grant USB and Serial permissions (one-time setup).
3. Run the application with `bash run.sh`.

---

This project uses a **Self-Contained Hardware Backend**. If the system-wide NI-VISA driver is missing, the app automatically falls back to a portable Python-based driver (`pyvisa-py`).

## Documentation & Support
*   **Need help with permissions or COM ports?** See the **[Deployment Guide](DEPLOYMENT.md)**.
*   **Something not connecting?** Check the **[Troubleshooting Checklist](DEPLOYMENT.md#troubleshooting-checklist)**.