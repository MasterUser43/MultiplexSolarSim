"""
Background sweep worker (QThread) and pixel configuration.

Thread Safety & Hardware Rules:
  1. Don't touch the Keithley or Relay from the GUI thread while a sweep is running. 
     Only one thread can talk to the instruments at a time.
  2. Never modify GUI widgets directly from this thread. Use Qt signals instead.
  3. Keep the sweep loop inside a try/finally block so the Keithley output and 
     relays are safely turned off if the sweep is aborted or hits an error.
"""
import time

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from core.pv_math import extract_parameters, check_fault
from instruments.keithley2460 import (
    init_keithley,
    keithley_output_safe,
    keithley_output_enable,
    keithley_read_current,
    keithley_source_voltage,
)
from instruments.numato_relay import (
    RELAY_SETTLE_S,
    numato_relay_token,
    numato_command,
    all_pixels_disconnect,
    connect_pixel,
)

PIXEL_LABELS = [chr(ord("A") + i) for i in range(12)]
PIXEL_TO_RELAY_CHANNEL = {label: i for i, label in enumerate(PIXEL_LABELS)}

DEFAULT_AREA_6_PIXEL_CM2 = 0.0396
DEFAULT_AREA_12_PIXEL_CM2 = 0.108


def active_pixel_labels(pixel_mode_text):
    count = 6 if pixel_mode_text.startswith("6") else 12
    return PIXEL_LABELS[:count]


def default_pixel_area(pixel_mode_text):
    if pixel_mode_text.startswith("6"):
        return DEFAULT_AREA_6_PIXEL_CM2
    return DEFAULT_AREA_12_PIXEL_CM2


class MeasurementWorker(QThread):
    """Runs one full sweep (all loops x all selected pixels) off the GUI thread."""

    log = pyqtSignal(str)
    pixel_started = pyqtSignal(str)
    pixel_result = pyqtSignal(dict)                     # successful pixel/loop -> full record
    pixel_faulted = pyqtSignal(str, float, str, int)    # pixel, area, fault, loop_number
    finished_sweep = pyqtSignal(bool, bool)             # (aborted, had_error)

    def __init__(self, keithley, relay, selected_pixels, sweep_params, parent=None):
        super().__init__(parent)
        self.keithley = keithley
        self.relay = relay
        self.selected_pixels = selected_pixels  # list of (pixel_label, channel, area_cm2)
        # sweep_params keys: v0, v1, reverse, pin, compliance_a, point_delay_s, loops, points
        self.params = sweep_params
        self._abort = False

    def request_abort(self):
        self._abort = True

    def _log_current_outliers(self, pixel, V, I, area):
        if len(I) < 5:
            return
        J = np.abs((I / area) * 1000)
        finite = np.isfinite(J)
        if not np.any(finite):
            return
        median = np.nanmedian(J[finite])
        peak_idx = int(np.nanargmax(J))
        peak = J[peak_idx]
        if median > 0 and peak > max(5 * median, 50):
            self.log.emit(
                f"WARNING: {pixel} current-density spike at {V[peak_idx]:.3f} V: "
                f"{peak:.2f} mA/cm^2 vs median {median:.2f} mA/cm^2"
            )

    def run(self):
        p = self.params
        measurement_error = False

        try:
            # Initialize Keithley to 0V and set the current limit 
            init_keithley(self.keithley, compliance_a=p["compliance_a"], logger=self.log.emit)
            self.log.emit(f"Keithley current compliance set to {p['compliance_a']:.6f} A")

            for loop_idx in range(p["loops"]):
                if self._abort:
                    break
                self.log.emit(f"Starting loop {loop_idx + 1} of {p['loops']}")

                for pixel, ch, area in self.selected_pixels:
                    if self._abort:
                        break

                    relay_token = numato_relay_token(ch)
                    self.log.emit(f"Measuring pixel {pixel} on relay channel {ch} ({relay_token})")
                    self.pixel_started.emit(pixel)

                    # --- HARDWARE INTERLOCK: SAFE SWITCHING SEQUENCE ---
                    # To prevent relay arcing and protect the solar cell:
                    # 1. Bring Keithley to 0V and turn output OFF.
                    # 2. Isolate all pixels to open-circuit.
                    # 3. Wait for mechanical contacts to physically settle (RELAY_SETTLE_S).
                    # 4. Connect target pixel, wait again, and only then enable Keithley output.

                    keithley_output_safe(self.keithley)
                    all_pixels_disconnect(self.relay)
                    time.sleep(RELAY_SETTLE_S)
                    connect_pixel(self.relay, ch)
                    time.sleep(RELAY_SETTLE_S)
                    keithley_output_enable(self.keithley, logger=self.log.emit)

                    # --- ACTIVE VOLTAGE SWEEP LOOP ---
                    sweep_start, sweep_end = (p["v1"], p["v0"]) if p["reverse"] else (p["v0"], p["v1"])
                    V = np.linspace(sweep_start, sweep_end, p["points"])
                    V_keithley = []
                    I = []
                    self.log.emit(
                        f"Sweep {pixel} device voltage: {sweep_start:.3f} V -> {sweep_end:.3f} V "
                        f"({p['points']} points, {'reverse' if p['reverse'] else 'forward'})"
                    )

                    for point_idx, v in enumerate(V):
                        if self._abort:
                            break
                        current, raw, keithley_v = keithley_read_current(
                            self.keithley, v, p["point_delay_s"]
                        )
                        V_keithley.append(keithley_v)

                        # Print raw responses for debugging first and intermediate points

                        if point_idx == 0:
                            self.log.emit(f"First raw Keithley current response for {pixel}: {raw}")
                        if point_idx in {0, len(V) // 2, len(V) - 1}:
                            try:
                                source_check = keithley_source_voltage(self.keithley)
                                self.log.emit(
                                    f"{pixel} source check point {point_idx + 1}: "
                                    f"device {v:.4f} V, Keithley command {keithley_v:.4f} V, "
                                    f"Keithley setpoint {source_check:.4f} V"
                                )
                            except Exception as e:
                                self.log.emit(f"WARNING: could not query Keithley source voltage: {e}")
                        I.append(current)

                    # --- POST-SWEEP SAFE STATE ---
                    # Immediately kill output and isolate the relay contacts

                    keithley_output_safe(self.keithley)
                    numato_command(self.relay, f"relay off {numato_relay_token(ch)}")
                    time.sleep(RELAY_SETTLE_S)

                    if self._abort:
                        break

                    I = np.asarray(I, dtype=float)
                    V_keithley = np.asarray(V_keithley, dtype=float)
                    self._log_current_outliers(pixel, V, I, area)

                    # Check for short or open circuit faults before doing math

                    fault = check_fault(I)
                    if fault:
                        self.pixel_faulted.emit(pixel, area, fault, loop_idx + 1)
                        self.log.emit(f"Pixel {pixel} flagged as {fault}")
                        continue

                    # Extract J-V metrics and dispatch them to the GUI
                    metrics = extract_parameters(V, I, area, p["pin"])
                    J = (I / area) * 1000

                    record = {
                        "pixel": pixel,
                        "channel": ch,
                        "loop": loop_idx + 1,
                        "area_cm2": area,
                        "pin_mw_cm2": p["pin"],
                        "voltage_v": V.tolist(),
                        "keithley_voltage_v": V_keithley.tolist(),
                        "current_a": I.tolist(),
                        "current_density_ma_cm2": J.tolist(),
                        **metrics,
                    }
                    self.pixel_result.emit(record)
                    self.log.emit(
                        f"Pixel {pixel}: Voc={metrics['Voc']:.3f} V, "
                        f"Jsc={metrics['Jsc']:.3f} mA/cm^2, "
                        f"PCE={metrics['PCE']:.2f}%"
                    )

        except Exception as e:
            measurement_error = True
            self.log.emit(f"ERROR: measurement stopped: {e}")
        finally:
            # --- GUARANTEED HARDWARE TEARDOWN ---
            # Ensures relays and Keithley default back to off, even on catastrophic crash or abort
            try:
                keithley_output_safe(self.keithley)
                all_pixels_disconnect(self.relay)
            except Exception:
                pass
            self.finished_sweep.emit(self._abort, measurement_error)
