"""
Pixel/channel configuration and the background sweep worker.

Threading Contract:
  - The GUI hands open instrument objects to the Worker.
    The GUI must not access these instruments until the finished_sweep signal fires.
  - The Worker never touches PyQt widgets. All updates are sent via signals to be handled 
    by the GUI thread.
  - worker.request_abort() sets a flag checked between points/pixels. The Worker's 
    try/finally block ensures hardware is safely safed even if aborted or faulted.
"""
import time

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from core.pv_math import extract_parameters, check_fault
from instruments.keithley2460 import (
    init_keithley,
    keithley_output_safe,
    keithley_output_enable,
    keithley_run_onchip_sweep,
    KEITHLEY_VOLTAGE_FROM_DEVICE_VOLTAGE,
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

                    # --- Cold-Switching Sequence ---
                    # To prevent relay arcing and protect the DUT from voltage spikes:
                    # Ensure 0V/Output OFF before switching mechanical relay contacts.

                    keithley_output_safe(self.keithley)
                    all_pixels_disconnect(self.relay)
                    time.sleep(RELAY_SETTLE_S)
                    connect_pixel(self.relay, ch)
                    time.sleep(RELAY_SETTLE_S)
                    keithley_output_enable(self.keithley, logger=self.log.emit)

                    sweep_start, sweep_end = (p["v1"], p["v0"]) if p["reverse"] else (p["v0"], p["v1"])
                    self.log.emit(
                        f"Sweep {pixel} device voltage: {sweep_start:.3f} V -> {sweep_end:.3f} V "
                        f"({p['points']} points, {'reverse' if p['reverse'] else 'forward'}, on-chip)"
                    )

                    # Run hardware-timed sweep. Note: This blocks until completion, 
                    # meaning the abort signal is only checked between pixel sweeps.
                    V_list, I_list = keithley_run_onchip_sweep(
                        self.keithley,
                        sweep_start,
                        sweep_end,
                        p["points"],
                        p["point_delay_s"],
                        compliance_a=p["compliance_a"],
                        logger=self.log.emit,
                    )
                    V = np.asarray(V_list, dtype=float)
                    I = np.asarray(I_list, dtype=float)
                    V_keithley = V * KEITHLEY_VOLTAGE_FROM_DEVICE_VOLTAGE
                    self.log.emit(
                        f"{pixel}: on-chip sweep returned {len(V)} points, "
                        f"V {V.min():.4f}..{V.max():.4f} V, I {I.min():.6g}..{I.max():.6g} A"
                    )

                    keithley_output_safe(self.keithley)
                    numato_command(self.relay, f"relay off {numato_relay_token(ch)}")
                    time.sleep(RELAY_SETTLE_S)

                    if self._abort:
                        break

                    self._log_current_outliers(pixel, V, I, area)

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
