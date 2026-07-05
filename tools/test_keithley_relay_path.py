"""
Bench test for Keithley HI -> Numato NO -> relay COM voltage path.

Default test:
    - Connect to Keithley 2460 over VISA
    - Connect to Numato relay board on COM3
    - Configure Keithley to source 1.0 V with 105 mA current limit
    - Turn all relays OFF
    - Turn Keithley output ON
    - Turn selected relay ON and pause for DMM checks
    - Turn selected relay OFF and pause for DMM checks
    - Cleanup: Keithley output OFF and all relays OFF

Run from the Code folder:
    .\venv\Scripts\python.exe .\test_keithley_relay_path.py

Suggested DMM checks relative to Keithley LO / shared bottom electrode:
    Relay ON:
        Keithley HI -> LO should be near source voltage
        Relay NO   -> LO should be near source voltage
        Relay COM  -> LO should be near source voltage

    Relay OFF:
        Keithley HI -> LO should still be near source voltage while output is ON
        Relay NO   -> LO should still be near source voltage
        Relay COM  -> LO should be floating/open if NC is unconnected
"""

import argparse
import time

import pyvisa
import serial


NUMATO_BAUD_RATE = 19200
NUMATO_RELAY_COUNT = 16


def relay_token(channel):
    if not 0 <= channel < NUMATO_RELAY_COUNT:
        raise ValueError(f"Relay channel must be 0 through {NUMATO_RELAY_COUNT - 1}.")
    return str(channel) if channel < 10 else chr(ord("A") + channel - 10)


def relay_command(port, command):
    if hasattr(port, "reset_input_buffer"):
        port.reset_input_buffer()
    port.write(f"{command}\r".encode("ascii"))
    port.flush()
    time.sleep(0.05)
    return port.read(64).decode(errors="replace").strip()


def find_keithley(resource_name=None):
    rm = pyvisa.ResourceManager()
    resources = rm.list_resources()
    if resource_name:
        inst = rm.open_resource(resource_name)
        return inst

    print("VISA resources:")
    for resource in resources:
        print(f"  {resource}")

    for resource in resources:
        try:
            inst = rm.open_resource(resource)
            idn = inst.query("*IDN?").strip()
            print(f"{resource}: {idn}")
            if "KEITHLEY" in idn.upper() and "2460" in idn:
                return inst
        except Exception as exc:
            print(f"{resource}: skipped ({exc})")

    raise RuntimeError("Keithley 2460 not found over VISA.")


def write_checked(inst, command):
    inst.write(command)
    try:
        err = inst.query(":SYST:ERR?").strip()
    except Exception as exc:
        print(f"  could not query error after {command}: {exc}")
        return

    if not (err.startswith("0") or "No error" in err):
        print(f"  Keithley error after {command}: {err}")


def configure_keithley(inst, voltage, current_limit):
    print("\nConfiguring Keithley 2460")
    inst.write("*RST")
    time.sleep(0.2)
    inst.write("*CLS")
    commands = [
        ':SENS:FUNC "CURR"',
        ":SENS:CURR:RANG:AUTO ON",
        ":SOUR:FUNC VOLT",
        f":SOUR:VOLT {voltage}",
        f":SOUR:VOLT:ILIM {current_limit}",
        ":OUTPut:STATe OFF",
    ]
    for command in commands:
        print(f"  {command}")
        write_checked(inst, command)


def pause(message, interactive):
    print(f"\n{message}")
    if interactive:
        input("Press Enter to continue...")
    else:
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description="Test Keithley-to-Numato relay voltage path.")
    parser.add_argument("--port", default="COM3", help="Numato COM port, default: COM3")
    parser.add_argument("--relay", type=int, default=0, help="Relay channel to test, default: 0")
    parser.add_argument("--voltage", type=float, default=1.0, help="Keithley source voltage, default: 1.0 V")
    parser.add_argument("--ilim", type=float, default=0.105, help="Keithley current limit in A, default: 0.105")
    parser.add_argument("--resource", default=None, help="Optional explicit VISA resource string")
    parser.add_argument("--no-prompt", action="store_true", help="Use timed pauses instead of Enter prompts")
    args = parser.parse_args()

    token = relay_token(args.relay)
    interactive = not args.no_prompt

    keithley = None
    relay = None
    try:
        keithley = find_keithley(args.resource)
        print("Using Keithley:", keithley.query("*IDN?").strip())

        print(f"\nOpening Numato relay board on {args.port}")
        relay = serial.Serial(args.port, NUMATO_BAUD_RATE, timeout=0.25, write_timeout=1)

        print("Turning all relays OFF")
        relay_command(relay, "relay writeall 0000")

        configure_keithley(keithley, args.voltage, args.ilim)

        print("\nTurning Keithley output ON")
        write_checked(keithley, ":OUTPut:STATe ON")
        print("Keithley output state:", keithley.query(":OUTPut:STATe?").strip())

        pause(
            "DMM check 1: Keithley HI -> LO and relay NO -> LO should both be near "
            f"{args.voltage:.3f} V. Relay COM should be floating if relay is OFF.",
            interactive,
        )

        print(f"\nTurning relay {args.relay} ({token}) ON")
        relay_command(relay, f"relay on {token}")
        pause(
            "DMM check 2: relay NO -> LO and relay COM -> LO should both be near "
            f"{args.voltage:.3f} V while the relay is ON.",
            interactive,
        )

        print(f"\nTurning relay {args.relay} ({token}) OFF")
        relay_command(relay, f"relay off {token}")
        pause(
            "DMM check 3: relay NO -> LO should still be near the Keithley voltage; "
            "relay COM -> LO should now be floating/open again.",
            interactive,
        )

    finally:
        print("\nCleanup")
        if keithley is not None:
            try:
                keithley.write(":SOUR:VOLT 0")
                time.sleep(0.1)
                keithley.write(":OUTPut:STATe OFF")
                print("  Keithley output OFF")
            except Exception as exc:
                print(f"  Keithley cleanup failed: {exc}")

        if relay is not None:
            try:
                relay_command(relay, "relay writeall 0000")
                relay.close()
                print("  All relays OFF")
            except Exception as exc:
                print(f"  Relay cleanup failed: {exc}")


if __name__ == "__main__":
    main()
