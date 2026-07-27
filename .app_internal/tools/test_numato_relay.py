"""
Command-line Numato 16-channel USB relay test.

Default behavior:
    - Open COM3 at 19200 baud
    - Turn all relays off
    - Switch relay 0 through relay 15 one at a time
    - Hold each relay on for 1 second, then turn it off
    - Repeat the full sequence 2 times

Run from the MultiplexSolarSim parent folder:
    .\Code\venv\Scripts\python.exe .\test_numato_relay.py

Run from the Code folder:
    .\venv\Scripts\python.exe ..\test_numato_relay.py
"""

import argparse
import time

import serial


BAUD_RATE = 19200
RELAY_COUNT = 16


def relay_token(channel):
    """Numato addresses relay 10-15 as A-F."""
    if not 0 <= channel < RELAY_COUNT:
        raise ValueError(f"Relay channel must be 0 through {RELAY_COUNT - 1}.")
    return str(channel) if channel < 10 else chr(ord("A") + channel - 10)


def send_command(port, command, read_bytes=64):
    """Send one Numato ASCII command and return any response text."""
    if hasattr(port, "reset_input_buffer"):
        port.reset_input_buffer()
    port.write(f"{command}\r".encode("ascii"))
    port.flush()
    time.sleep(0.03)
    return port.read(read_bytes).decode(errors="replace").strip()


def all_relays_off(port):
    return send_command(port, "relay writeall 0000")


def test_relays(port_name, cycles, delay_s):
    print(f"Opening Numato relay board on {port_name} at {BAUD_RATE} baud")
    with serial.Serial(port_name, BAUD_RATE, timeout=0.25, write_timeout=1) as port:
        print("Turning all relays OFF")
        response = all_relays_off(port)
        if response:
            print(f"  response: {response}")

        for cycle in range(1, cycles + 1):
            print(f"\nCycle {cycle} of {cycles}")

            for channel in range(RELAY_COUNT):
                token = relay_token(channel)
                print(f"  relay {channel:02d} token {token}: ON")
                response = send_command(port, f"relay on {token}")
                if response:
                    print(f"    response: {response}")

                time.sleep(delay_s)

                print(f"  relay {channel:02d} token {token}: OFF")
                response = send_command(port, f"relay off {token}")
                if response:
                    print(f"    response: {response}")

        print("\nFinal cleanup: turning all relays OFF")
        response = all_relays_off(port)
        if response:
            print(f"  response: {response}")

    print("Relay test complete.")


def main():
    parser = argparse.ArgumentParser(description="Test a Numato 16-channel USB relay board.")
    parser.add_argument("--port", default="COM3", help="Serial COM port, default: COM3")
    parser.add_argument("--cycles", type=int, default=2, help="Number of full relay passes, default: 2")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to hold each relay ON, default: 1.0")
    args = parser.parse_args()

    if args.cycles < 1:
        raise ValueError("--cycles must be at least 1")
    if args.delay < 0:
        raise ValueError("--delay must be non-negative")

    test_relays(args.port, args.cycles, args.delay)


if __name__ == "__main__":
    main()
