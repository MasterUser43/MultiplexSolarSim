"""
Keithley 2460 SourceMeter driver: VISA discovery, SCPI setup, output
control, and point-by-point sweep reads.
"""
import time

import pyvisa

KEITHLEY_SAFE_VOLTAGE = 0.0
KEITHLEY_DEFAULT_COMPLIANCE_A = 0.105
KEITHLEY_OUTPUT_SETTLE_S = 0.15

# Wiring convention:
#   relay NO bus -> Keithley Force HI -> selected individual n-side pixel
#   shared p-side electrode -> Keithley Force LO
# GUI voltage is device voltage V(p-side shared electrode) - V(n-side pixel).
# Keithley source voltage is V(HI) - V(LO), so it is the negative of device voltage.
KEITHLEY_VOLTAGE_FROM_DEVICE_VOLTAGE = -1.0


def find_keithley(resource_name=None, logger=None):
    """
    Locates the Keithley 2460.
    """
    backend_note = "NI-VISA"
    try:
        # 1. Try to use the standard NI-VISA backend (the 800MB driver)
        rm = pyvisa.ResourceManager()
    except Exception:
        # 2. Fallback: Use the 'pyvisa-py' backend
        backend_note = "pyvisa-py (self-contained)"
        try:
            import libusb_package
            rm = pyvisa.ResourceManager('@py')
        except Exception:
            raise RuntimeError(
                "No VISA driver found. Please run install.bat to set up "
                "local drivers or install NI-VISA."
            )

    if logger:
        logger(f"VISA backend: {backend_note}")

    # If the user provided a specific ID (like 'USB0::0x05E6::...'), use it directly
    if resource_name:
        return rm.open_resource(resource_name)

    # 3. Discovery Loop: USB instruments only.
    for r in rm.list_resources('USB?*::INSTR'):
        try:
            inst = rm.open_resource(r)
            inst.timeout = 2000 # 2-second limit
            
            idn = inst.query("*IDN?").upper()
            
            # Look for Keithley and the specific model number 2460
            if "KEITHLEY" in idn and "2460" in idn:
                return inst
            
            inst.close() # Close connection if it's not the right device
        except Exception:
            continue
            
    raise RuntimeError("Keithley 2460 not found. Check USB connection and power.")


def keithley_system_error(k):
    try:
        return k.query(":SYST:ERR?").strip()
    except Exception as e:
        return f"Could not query Keithley error queue: {e}"


def keithley_log_errors(k, logger=None, context="Keithley"):
    errors = []
    for _ in range(8):
        err = keithley_system_error(k)
        errors.append(err)
        if err.startswith("0") or "No error" in err:
            break
    if logger:
        for err in errors:
            logger(f"{context} error queue: {err}")
    return errors


def keithley_write_checked(k, command, logger=None):
    k.write(command)
    err = keithley_system_error(k)
    if logger and not (err.startswith("0") or "No error" in err):
        logger(f"Keithley rejected command {command!r}: {err}")
    return err


def keithley_output_state(k):
    response = k.query(":OUTPut:STATe?").strip()
    return response.startswith("1") or response.upper().startswith("ON")


def keithley_set_output(k, enabled, logger=None):
    state = "ON" if enabled else "OFF"
    keithley_write_checked(k, f":OUTPut:STATe {state}", logger=logger)
    time.sleep(KEITHLEY_OUTPUT_SETTLE_S)

    try:
        actual_state = keithley_output_state(k)
        if logger:
            logger(f"Keithley output {'ON' if actual_state else 'OFF'} after command {state}")
        if enabled and not actual_state:
            raise RuntimeError("Keithley did not report output ON after :OUTPut:STATe ON.")
    except Exception as e:
        if logger:
            logger(f"WARNING: could not verify Keithley output state: {e}")
        if enabled:
            raise


def init_keithley(k, compliance_a=KEITHLEY_DEFAULT_COMPLIANCE_A, logger=None):
    compliance_a = max(float(compliance_a), 1e-9)
    k.write("*RST")
    time.sleep(0.2)
    k.write("*CLS")

    commands = [
        ":SENS:FUNC \"CURR\"",
        ":SENS:CURR:RANG:AUTO ON",
        ":SOUR:FUNC VOLT",
        f":SOUR:VOLT {KEITHLEY_SAFE_VOLTAGE}",
        f":SOUR:VOLT:ILIM {compliance_a}",
        ":OUTPut:STATe OFF",
    ]
    for command in commands:
        keithley_write_checked(k, command, logger=logger)

    keithley_log_errors(k, logger=logger, context="Keithley setup")


def keithley_output_safe(k):
    k.write(f":SOUR:VOLT {KEITHLEY_SAFE_VOLTAGE}")
    time.sleep(KEITHLEY_OUTPUT_SETTLE_S)
    keithley_set_output(k, False)


def keithley_output_enable(k, logger=None):
    keithley_set_output(k, True, logger=logger)


def parse_keithley_current(raw):
    # For the 2460, when SENS:FUNC is CURR, READ? returns the active
    # measurement reading first. Additional fields, if present, are metadata.
    for part in raw.split(","):
        try:
            return float(part.strip())
        except ValueError:
            continue
    raise RuntimeError(f"Could not parse Keithley reading: {raw}")


def keithley_source_voltage(k):
    return float(k.query(":SOUR:VOLT?").strip().split(",")[0])


def keithley_voltage_for_device_voltage(device_voltage):
    return KEITHLEY_VOLTAGE_FROM_DEVICE_VOLTAGE * device_voltage


def keithley_read_current(k, device_voltage, point_delay_s):
    keithley_voltage = keithley_voltage_for_device_voltage(device_voltage)
    k.write(f":SOUR:VOLT {keithley_voltage}")
    time.sleep(point_delay_s)
    k.write(":READ?")
    raw = k.read().strip()
    return parse_keithley_current(raw), raw, keithley_voltage
