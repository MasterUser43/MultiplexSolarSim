"""
Pixel/channel configuration shared between the GUI and the measurement
orchestration.

NOTE: This module is intentionally thin for now. The actual sweep
orchestration (looping over pixels/loops, driving the Keithley and relay,
collecting data) still lives in gui/app_window.py's GUI.run_measurement().

That method reaches directly into GUI state (self.log_message,
self.current_pixel_label, self.abort_flag, QApplication.processEvents())
and needs to be decoupled from those before it can move here as a
QThread-safe worker. 

This module is where the QThread worker will live once that decoupling pass happens.
Thank you for your patience :)
"""

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
