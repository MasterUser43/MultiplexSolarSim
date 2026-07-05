# Multiplex Solar Simulator - IV Characterization

Python/PyQt5 GUI for automated multi-pixel solar cell IV characterization. Integrates a **Keithley 2460 SMU** and a **Numato 16-channel USB relay** for multiplexed testing.

## Hardware Requirements
1. **Keithley 2460 SourceMeter** (USB).
2. **Numato 16-Channel USB Relay Board**.
3. **NI-VISA Runtime:** Essential for SMU communication. [Download here](https://www.ni.com/en-us/support/downloads/drivers/download.ni-visa.html).

## Driver & Setup Notes
- **Numato Relay:** On Linux, the relay usually works out-of-the-box as a CDC-ACM device (`/dev/ttyACM0`). If the device is not recognized or you are moving to Windows, you may need the Numato CDC drivers. Drivers can be found on the [Numato Lab Website](https://numato.com/product/16-channel-usb-relay-module#downloads).

## Installation
1. Clone the repository:
```bash
   git clone https://github.com/MasterUser43/MultiplexSolarSim.git
   cd MultiplexSolarSim
```

2. Install Python dependencies:
```bash
   pip install -r requirements.txt
```

## Usage
```bash
   python SolarGUIv2.py
```

