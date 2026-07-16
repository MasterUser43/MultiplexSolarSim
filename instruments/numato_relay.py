"""
Numato 16-channel USB relay driver: board auto-detection and channel
on/off commands.
"""
import time

import serial
import serial.tools.list_ports

NUMATO_BAUD_RATE = 19200
NUMATO_VENDOR_ID = 0x2A19
NUMATO_PRODUCT_ID = 0x0C03
NUMATO_RELAY_COUNT = 16
RELAY_SETTLE_S = 0.15


def find_numato():
    ports = list(serial.tools.list_ports.comports())
    preferred_ports = [
        p for p in ports
        if (p.vid == NUMATO_VENDOR_ID and p.pid == NUMATO_PRODUCT_ID)
        or "numato" in " ".join(str(v) for v in (p.manufacturer, p.description, p.product)).lower()
    ]

    for p in preferred_ports + [p for p in ports if p not in preferred_ports]:
        try:
            ser = serial.Serial(
                p.device,
                NUMATO_BAUD_RATE,
                timeout=0.25,
                write_timeout=1,
            )
            if hasattr(ser, "reset_input_buffer"):
                ser.reset_input_buffer()
            return ser
        except Exception:
            continue
    raise RuntimeError("Relay not found")


def numato_relay_token(ch):
    if not isinstance(ch, int) or not 0 <= ch < NUMATO_RELAY_COUNT:
        raise ValueError(f"Relay channel must be an integer from 0 to {NUMATO_RELAY_COUNT - 1}.")
    return str(ch) if ch < 10 else chr(ord("A") + ch - 10)


def numato_command(r, command):
    if hasattr(r, "reset_input_buffer"):
        r.reset_input_buffer()
    r.write(f"{command}\r".encode())
    r.flush()
    time.sleep(0.03)
    return r.read(64).decode(errors="replace").strip()


def all_pixels_disconnect(r, n=None):
    """Turn all relays off.

    With NC terminals left unconnected, this leaves every pixel top contact
    floating/isolated until its relay is switched ON to Keithley HI.
    """
    numato_command(r, "relay writeall 0000")


def connect_pixel(r, ch):
    numato_command(r, f"relay on {numato_relay_token(ch)}")
