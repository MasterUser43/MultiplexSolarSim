from cProfile import label
import os
import sys
import time

import numpy as np
import pyqtgraph as pg
import pyvisa
import serial
import serial.tools.list_ports

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import *


# =========================
# HARDWARE
# =========================

NUMATO_BAUD_RATE = 19200
NUMATO_VENDOR_ID = 0x2A19
NUMATO_PRODUCT_ID = 0x0C03
NUMATO_RELAY_COUNT = 16
PIXEL_LABELS = [chr(ord("A") + i) for i in range(12)]
PIXEL_TO_RELAY_CHANNEL = {label: i for i, label in enumerate(PIXEL_LABELS)}
DEFAULT_AREA_6_PIXEL_CM2 = 0.0396
DEFAULT_AREA_12_PIXEL_CM2 = 0.108
KEITHLEY_SAFE_VOLTAGE = 0.0
KEITHLEY_DEFAULT_COMPLIANCE_A = 0.105
KEITHLEY_OUTPUT_SETTLE_S = 0.15
RELAY_SETTLE_S = 0.15
# Wiring convention:
#   relay NO bus -> Keithley Force HI -> selected individual n-side pixel
#   shared p-side electrode -> Keithley Force LO
# GUI voltage is device voltage V(p-side shared electrode) - V(n-side pixel).
# Keithley source voltage is V(HI) - V(LO), so it is the negative of device voltage.
KEITHLEY_VOLTAGE_FROM_DEVICE_VOLTAGE = -1.0


class InstrumentManager:
    def __init__(self):
        self.keithley = None
        self.relay = None

    def connect_all(self, logger=None):
        self.keithley = None
        self.relay = None

        try:
            self.keithley = find_keithley()
            if logger:
                logger("OK: Keithley connected")
        except Exception as e:
            if logger:
                logger(f"ERROR: Keithley connection failed: {e}")

        try:
            self.relay = find_numato()
            if logger:
                logger(f"OK: Numato relay connected on {self.relay.port}")
        except Exception as e:
            if logger:
                logger(f"ERROR: Relay connection failed: {e}")

        return self.keithley is not None, self.relay is not None


def find_keithley():
    rm = pyvisa.ResourceManager()
    for r in rm.list_resources():
        try:
            inst = rm.open_resource(r)
            if "KEITHLEY" in inst.query("*IDN?").upper():
                return inst
        except Exception:
            continue
    raise RuntimeError("Keithley not found")


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


def active_pixel_labels(pixel_mode_text):
    count = 6 if pixel_mode_text.startswith("6") else 12
    return PIXEL_LABELS[:count]


def default_pixel_area(pixel_mode_text):
    if pixel_mode_text.startswith("6"):
        return DEFAULT_AREA_6_PIXEL_CM2
    return DEFAULT_AREA_12_PIXEL_CM2


# =========================
# PV METRICS
# =========================

def _interp_zero_crossing(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]

    if len(x) < 2:
        return np.nan

    exact = np.where(np.isclose(y, 0.0, atol=1e-15))[0]
    if exact.size:
        return float(x[exact[0]])

    sign_changes = np.where(np.diff(np.signbit(y)))[0]
    if sign_changes.size == 0:
        return np.nan

    idx = sign_changes[0]
    x0, x1 = x[idx], x[idx + 1]
    y0, y1 = y[idx], y[idx + 1]
    if np.isclose(y1, y0):
        return float((x0 + x1) / 2)
    return float(x0 + (0 - y0) * (x1 - x0) / (y1 - y0))


def extract_parameters(V, I, area_cm2, pin_mw_cm2=100):
    V = np.asarray(V, dtype=float)
    I = np.asarray(I, dtype=float)

    if area_cm2 <= 0:
        raise ValueError("Pixel area must be greater than zero.")
    if pin_mw_cm2 <= 0:
        raise ValueError("Incident power must be greater than zero.")

    # J is in mA/cm^2 because A/cm^2 * 1000 = mA/cm^2.
    J = (I / area_cm2) * 1000

    order_v = np.argsort(V)
    V_sorted = V[order_v]
    J_sorted = J[order_v]
    I_sorted = I[order_v]

    Voc = _interp_zero_crossing(V_sorted, I_sorted)
    Jsc_raw = _interp_zero_crossing(J_sorted, V_sorted)
    Jsc = abs(Jsc_raw) if np.isfinite(Jsc_raw) else np.nan

    # Electrical power density is V * J in mW/cm^2. The generated-power
    # quadrant is determined from the short-circuit current polarity, then
    # restricted to the photovoltaic operating region between 0 V and Voc.
    measured_power = V * J
    if np.isfinite(Jsc_raw) and not np.isclose(Jsc_raw, 0.0):
        current_polarity = np.sign(Jsc_raw)
    else:
        current_polarity = -1 if abs(np.nanmin(measured_power)) > abs(np.nanmax(measured_power)) else 1
    power_density = current_polarity * measured_power

    finite = np.isfinite(V) & np.isfinite(power_density)
    if np.isfinite(Voc):
        lo, hi = sorted((0.0, Voc))
        operating_region = finite & (V >= lo) & (V <= hi)
    else:
        operating_region = finite
    positive_region = operating_region & (power_density >= 0)
    candidates = np.where(positive_region)[0]
    if candidates.size == 0:
        candidates = np.where(finite)[0]
    if candidates.size == 0:
        raise ValueError("No finite IV data available for metric extraction.")

    mpp_idx = int(candidates[np.nanargmax(power_density[candidates])])
    Pmax = max(float(power_density[mpp_idx]), 0.0)
    Vmpp = float(V[mpp_idx])
    Jmpp = abs(float(J[mpp_idx]))

    denom = abs(Voc * Jsc) if np.isfinite(Voc) and np.isfinite(Jsc) else np.nan
    FF = Pmax / denom if denom and np.isfinite(denom) else np.nan
    PCE = (Pmax / pin_mw_cm2) * 100

    return {
        "Voc": float(Voc),
        "Jsc": float(Jsc),
        "Vmpp": Vmpp,
        "Jmpp": Jmpp,
        "Pmax": Pmax,
        "FF": float(FF),
        "PCE": float(PCE),
    }


def check_fault(I):
    I = np.asarray(I, dtype=float)
    if np.max(np.abs(I)) > 0.95:
        return "SHORT"
    if np.max(np.abs(I)) < 1e-6:
        return "OPEN"
    return None


# =========================
# GUI
# =========================

class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelViewBox(pg.ViewBox):
    def __init__(self, range_callback=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.range_callback = range_callback

    def wheelEvent(self, event, axis=None):
        event.ignore()

    def mouseClickEvent(self, event):
        if event.button() == Qt.RightButton and self.range_callback:
            event.accept()
            self.range_callback()
            return
        super().mouseClickEvent(event)


class GUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Multiplex Solar Simulator - IV Characterization")
        self.resize(1720, 1200)
        self.setMinimumSize(1650, 1160)
        self.setObjectName("Root")

        self.inst = InstrumentManager()
        self.abort_flag = False
        self.results = []
        self.output_dir = os.getcwd()
        self.curves = {}
        self.pixel_colors = [
            "#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#004c6d", "#a05195",
        ]
        self.loop_dash_patterns = [
            None,  # Loop 1: solid
            [7, 4],  # Loop 2: dashed
            [1, 3],  # Loop 3: dotted
            [7, 3, 1.5, 3, 7, 5],  # Loop 4: dash-dot-dash
            [7, 3, 1.5, 3, 1.5, 5],  # Loop 5: dash-dot-dot
            [12, 4],
            [4, 3],
            [10, 3, 3, 3],
        ]
        self.pixel_legend = None
        self.loop_legend = None

        self.apply_style()
        self.build_ui()
        QTimer.singleShot(0, self.refresh_startup_layout)

    def apply_style(self):
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet("""
            QWidget#Root {
                background: #f4f6f8;
                color: #1f2933;
            }
            QFrame#Header {
                background: #14213d;
                border: 0;
            }
            QLabel#Title {
                color: #ffffff;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#Subtitle {
                color: #c9d6e2;
                font-size: 11px;
                letter-spacing: 0px;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d9e2ec;
                border-radius: 6px;
                margin-top: 0px;
                padding: 18px 10px 10px 10px;
                font-weight: 700;
            }
            QGroupBox::title {
                subcontrol-origin: border;
                subcontrol-position: top left;
                top: 2px;
                left: 12px;
                padding: 0 3px;
                color: #243b53;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
                background: #ffffff;
                border: 1px solid #bcccdc;
                border-radius: 4px;
                padding: 5px 7px;
                selection-background-color: #3d5a80;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                min-height: 32px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border: 1px solid #2f80ed;
            }
            QPushButton {
                background: #e9eef4;
                border: 1px solid #c7d2df;
                border-radius: 4px;
                padding: 9px 14px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #dde7f2;
            }
            QPushButton:pressed {
                background: #c8d7e6;
            }
            QPushButton#PrimaryButton {
                background: #1b5e8c;
                border-color: #15486b;
                color: #ffffff;
            }
            QPushButton#PrimaryButton:hover {
                background: #236fa4;
            }
            QPushButton#DangerButton {
                background: #b42318;
                border-color: #8f1d15;
                color: #ffffff;
            }
            QPushButton#DangerButton:hover {
                background: #c9372c;
            }
            QLabel[status="ok"] {
                background: #e3f8ec;
                color: #17633a;
                border: 1px solid #a8e6bf;
                border-radius: 4px;
                padding: 5px 8px;
                font-weight: 700;
            }
            QLabel[status="bad"] {
                background: #fdecea;
                color: #9b1c1c;
                border: 1px solid #f4b4ad;
                border-radius: 4px;
                padding: 5px 8px;
                font-weight: 700;
            }
            QLabel[status="idle"] {
                background: #edf2f7;
                color: #4a5568;
                border: 1px solid #cbd5e0;
                border-radius: 4px;
                padding: 5px 8px;
                font-weight: 700;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d9e2ec;
                gridline-color: #e6ecf2;
                alternate-background-color: #f8fafc;
            }
            QHeaderView::section {
                background: #243b53;
                color: #ffffff;
                border: 0;
                padding: 7px;
                font-weight: 700;
            }
            QTextEdit {
                font-family: Consolas, "Courier New", monospace;
                font-size: 9pt;
                background: #0f172a;
                color: #dbeafe;
                border: 1px solid #1e293b;
            }
        """)

    def build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(10)

        main.addWidget(self.build_header())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)

        left_panel = QWidget()
        left_panel.setMinimumWidth(760)
        left_panel.setMaximumWidth(820)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_layout.addWidget(self.build_pixel_panel(), 1)
        left_layout.addWidget(self.build_sweep_panel(), 0)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(self.build_plot_panel(), 2)
        right_layout.addWidget(self.build_results_panel(), 5)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main.addWidget(splitter, 1)

        main.addWidget(self.build_log_panel())

    def build_header(self):
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(72)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(14)

        title_block = QVBoxLayout()
        title = QLabel("Multiplex Solar Simulator")
        title.setObjectName("Title")
        subtitle = QLabel("IV acquisition, multiplexing, and PV metrics")
        subtitle.setObjectName("Subtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        layout.addLayout(title_block, 0)

        self.keithley_status = QLabel("Keithley: not connected")
        self.relay_status = QLabel("Relay: not connected")
        self.keithley_status.setProperty("status", "idle")
        self.relay_status.setProperty("status", "idle")
        layout.addWidget(self.keithley_status)
        layout.addWidget(self.relay_status)

        self.connect_btn = QPushButton("Connect Instruments")
        self.connect_btn.setObjectName("PrimaryButton")
        self.connect_btn.clicked.connect(self.connect_instruments)
        layout.addWidget(self.connect_btn)
        layout.addStretch(1)

        return header

    def build_pixel_panel(self):
        group = QGroupBox("Pixel Selection")
        self.pixel_group = group
        group.setMinimumHeight(200)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 11, 14, 6)
        layout.setSpacing(4)

        row = QHBoxLayout()
        row.addWidget(QLabel("Array"))
        self.pixel_mode = NoWheelComboBox()
        self.pixel_mode.setFixedHeight(32)
        self.pixel_mode.addItems(["6 pixels", "12 pixels"])
        self.pixel_mode.currentIndexChanged.connect(self.build_pixels)
        row.addWidget(self.pixel_mode, 1)
        layout.addLayout(row)

        self.pixel_grid = QGridLayout()
        self.pixel_grid.setHorizontalSpacing(10)
        self.pixel_grid.setVerticalSpacing(4)

        # Left pair
        self.pixel_grid.setColumnMinimumWidth(0, 52)
        self.pixel_grid.setColumnMinimumWidth(1, 150)

        # Middle live-measurement label
        self.pixel_grid.setColumnMinimumWidth(2, 165)

        # Right pair
        self.pixel_grid.setColumnMinimumWidth(3, 52)
        self.pixel_grid.setColumnMinimumWidth(4, 150)

        self.pixel_grid.setColumnStretch(1, 1)
        self.pixel_grid.setColumnStretch(4, 1)

        layout.addLayout(self.pixel_grid)

        # Live measurement status label
        self.current_pixel_label = QLabel("Measuring pixel: --")
        self.current_pixel_label.setAlignment(Qt.AlignCenter)
        self.current_pixel_label.setStyleSheet("""
            color: #52606d;
            font-style: italic;
            font-size: 13px;
            padding-bottom: 2px;
        """)

        self.checks = []
        self.areas = []
        self.build_pixels()

        scroll = QScrollArea()
        self.pixel_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll.setWidget(group)
        return scroll

    def build_sweep_panel(self):
        group = QGroupBox("Sweep Setup")
        group.setFixedHeight(395)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 24, 14, 16)
        layout.setSpacing(14)

        form = QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(18)
        form.setContentsMargins(0, 8, 0, 8)
        form.setRowMinimumHeight(0, 48)
        form.setRowMinimumHeight(1, 48)
        form.setRowMinimumHeight(2, 48)
        form.setRowMinimumHeight(3, 48)
        form.setColumnMinimumWidth(0, 140)
        form.setColumnMinimumWidth(1, 205)
        form.setColumnMinimumWidth(2, 170)
        form.setColumnMinimumWidth(3, 205)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)

        for i in range(4):
            form.setRowStretch(i, 0)

        def add_field(row, col, label_text, widget):
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label.setFixedHeight(44)

            widget.setFixedHeight(44)

            form.addWidget(label, row, col)
            form.addWidget(widget, row, col + 1)

        self.v0 = NoWheelDoubleSpinBox()
        self.v0.setMinimumWidth(205)
        self.v0.setMinimumHeight(44)
        self.v0.setRange(-5, 5)
        self.v0.setDecimals(3)
        self.v0.setValue(-0.2)

        self.v1 = NoWheelDoubleSpinBox()
        self.v1.setMinimumWidth(205)
        self.v1.setMinimumHeight(44)
        self.v1.setRange(-5, 5)
        self.v1.setDecimals(3)
        self.v1.setValue(1.3)

        self.points = NoWheelSpinBox()
        self.points.setMinimumWidth(205)
        self.points.setMinimumHeight(44)
        self.points.setRange(2, 2000)
        self.points.setValue(100)

        self.loops = NoWheelSpinBox()
        self.loops.setMinimumWidth(205)
        self.loops.setMinimumHeight(44)
        self.loops.setRange(1, 20)
        self.loops.setValue(1)

        self.pin = NoWheelDoubleSpinBox()
        self.pin.setMinimumWidth(205)
        self.pin.setMinimumHeight(44)
        self.pin.setRange(0.001, 5000)
        self.pin.setDecimals(3)
        self.pin.setValue(100.0)

        self.compliance_ma = NoWheelDoubleSpinBox()
        self.compliance_ma.setMinimumWidth(205)
        self.compliance_ma.setMinimumHeight(44)
        self.compliance_ma.setRange(0.001, 1000)
        self.compliance_ma.setDecimals(3)
        self.compliance_ma.setValue(KEITHLEY_DEFAULT_COMPLIANCE_A * 1000)

        self.point_delay = NoWheelDoubleSpinBox()
        self.point_delay.setMinimumWidth(205)
        self.point_delay.setMinimumHeight(44)
        self.point_delay.setRange(0.001, 10)
        self.point_delay.setDecimals(3)
        self.point_delay.setValue(0.010)

        self.dir = NoWheelComboBox()
        self.dir.setMinimumWidth(205)
        self.dir.setMinimumHeight(44)
        self.dir.addItems(["Forward", "Reverse"])
        self.dir.setCurrentText("Reverse")

        add_field(0, 0, "From (V)", self.v0)
        add_field(0, 2, "To (V)", self.v1)
        add_field(1, 0, "Direction", self.dir)
        add_field(1, 2, "Points", self.points)
        add_field(2, 0, "Loops", self.loops)
        add_field(2, 2, "Irradiance (mW/cm^2)", self.pin)
        add_field(3, 0, "Compliance (mA)", self.compliance_ma)
        add_field(3, 2, "Point Delay (s)", self.point_delay)
        layout.addLayout(form)

        self.sweep_time_label = QLabel()
        self.sweep_time_label.setAlignment(Qt.AlignRight)
        self.sweep_time_label.setContentsMargins(0, 8, 0, 6)
        layout.addWidget(self.sweep_time_label)
        self.points.valueChanged.connect(self.update_sweep_time_estimate)
        self.point_delay.valueChanged.connect(self.update_sweep_time_estimate)
        self.update_sweep_time_estimate()

        self.auto_save = QCheckBox("Auto-save TXT after sweep")
        self.auto_save.setChecked(True)
        layout.addWidget(self.auto_save)

        buttons = QHBoxLayout()
        self.start = QPushButton("Start Sweep")
        self.start.setObjectName("PrimaryButton")
        self.abort = QPushButton("Abort")
        self.abort.setObjectName("DangerButton")
        self.save_btn = QPushButton("Export TXT")
        self.abort.setEnabled(False)
        self.save_btn.setEnabled(False)

        self.start.clicked.connect(self.run_measurement)
        self.abort.clicked.connect(self.abort_measurement)
        self.save_btn.clicked.connect(lambda: self.save_results(auto=False))

        buttons.addWidget(self.start)
        buttons.addWidget(self.abort)
        buttons.addWidget(self.save_btn)
        layout.addLayout(buttons)

        return group

    def build_plot_panel(self):
        group = QGroupBox("IV Curves")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 18, 12, 12)

        self.plot = pg.PlotWidget(viewBox=NoWheelViewBox(self.open_plot_range_dialog))
        self.plot.setBackground("#ffffff")
        self.plot.showGrid(x=True, y=True, alpha=0.22)
        self.plot.setLabel("bottom", "Voltage", units="V")
        self.plot.setLabel("left", "Current Density", units="mA/cm^2")
        self.plot.setMinimumHeight(300)
        self.plot.setMaximumHeight(340)
        self.plot.getAxis("bottom").setPen(pg.mkPen("#52606d"))
        self.plot.getAxis("left").setPen(pg.mkPen("#52606d"))
        self.plot.getAxis("bottom").setTextPen(pg.mkPen("#334e68"))
        self.plot.getAxis("left").setTextPen(pg.mkPen("#334e68"))
        self.apply_default_plot_range()
        layout.addWidget(self.plot)

        return group

    def apply_default_plot_range(self):
        self.plot.enableAutoRange(x=False, y=False)
        self.plot.setXRange(0, 1.3, padding=0)
        self.plot.setYRange(0, 26, padding=0)

    def pixel_color(self, channel):
        return self.pixel_colors[channel % len(self.pixel_colors)]

    def loop_pen(self, loop_number, color="#243b53", width=2):
        pattern = self.loop_dash_patterns[(int(loop_number) - 1) % len(self.loop_dash_patterns)]
        pen = pg.mkPen(color=color, width=width)

        if pattern is None:
            pen.setStyle(Qt.SolidLine)
        else:
            pen.setStyle(Qt.CustomDashLine)
            pen.setDashPattern(pattern)

        return pen

    def curve_pen(self, channel, loop_number):
        return self.loop_pen(loop_number, color=self.pixel_color(channel), width=2)

    def remove_legend(self, legend):
        if legend is None:
            return

        try:
            scene = legend.scene()
            if scene is not None:
                scene.removeItem(legend)
        except Exception:
            pass

        try:
            legend.setParentItem(None)
        except Exception:
            pass

    def clear_plot_legends(self):
        plot_item = self.plot.getPlotItem()
        existing = getattr(plot_item, "legend", None)
        self.remove_legend(existing)
        plot_item.legend = None

        if self.loop_legend is not None and self.loop_legend is not existing:
            self.remove_legend(self.loop_legend)

        self.pixel_legend = None
        self.loop_legend = None

    def reset_plot_legends(self, selected_pixels, loop_count):
        self.clear_plot_legends()

        self.pixel_legend = self.plot.addLegend(offset=(12, 12))
        for pixel, channel, _area in selected_pixels:
            item = pg.PlotDataItem([], [], pen=pg.mkPen(color=self.pixel_color(channel), width=2))
            self.pixel_legend.addItem(item, pixel)

        if loop_count > 1:
            self.loop_legend = pg.LegendItem(offset=(-12, 12))
            self.loop_legend.setParentItem(self.plot.getPlotItem().vb)
            for loop_number in range(1, loop_count + 1):
                item = pg.PlotDataItem([], [], pen=self.loop_pen(loop_number, width=2))
                self.loop_legend.addItem(item, f"Loop {loop_number}")

    def open_plot_range_dialog(self):
        view_range = self.plot.getViewBox().viewRange()
        (x_min_current, x_max_current), (y_min_current, y_max_current) = view_range

        dialog = QDialog(self)
        dialog.setWindowTitle("Set IV Plot Range")
        form = QFormLayout(dialog)

        x_min = NoWheelDoubleSpinBox()
        x_min.setRange(-1000, 1000)
        x_min.setDecimals(4)
        x_min.setValue(x_min_current)

        x_max = NoWheelDoubleSpinBox()
        x_max.setRange(-1000, 1000)
        x_max.setDecimals(4)
        x_max.setValue(x_max_current)

        y_min = NoWheelDoubleSpinBox()
        y_min.setRange(-100000, 100000)
        y_min.setDecimals(4)
        y_min.setValue(y_min_current)

        y_max = NoWheelDoubleSpinBox()
        y_max.setRange(-100000, 100000)
        y_max.setDecimals(4)
        y_max.setValue(y_max_current)

        form.addRow("Voltage min (V)", x_min)
        form.addRow("Voltage max (V)", x_max)
        form.addRow("J min (mA/cm^2)", y_min)
        form.addRow("J max (mA/cm^2)", y_max)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            if x_max.value() <= x_min.value() or y_max.value() <= y_min.value():
                self.log_message("ERROR: plot range maximum must be greater than minimum")
                return
            self.plot.setXRange(x_min.value(), x_max.value(), padding=0)
            self.plot.setYRange(y_min.value(), y_max.value(), padding=0)

    def build_results_panel(self):
        group = QGroupBox("Extracted Metrics")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 18, 12, 12)

        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels(
            ["Loop", "Pixel", "Area", "Voc (V)", "Jsc (mA/cm^2)", "FF",
             "PCE (%)", "Vmpp (V)", "Jmp (mA/cm^2)", "Pmax (mW/cm^2)", "Status"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(430)
        layout.addWidget(self.table)

        return group

    def build_log_panel(self):
        group = QGroupBox("Run Log")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 18, 12, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel("Sample ID"))
        self.file = QLineEdit("Sample")
        top.addWidget(self.file, 1)
        top.addWidget(QLabel("Save folder"))
        self.output_dir_field = QLineEdit(self.output_dir)
        self.output_dir_field.setReadOnly(True)
        top.addWidget(self.output_dir_field, 2)
        self.browse_dir_btn = QPushButton("Browse...")
        self.browse_dir_btn.clicked.connect(self.choose_output_dir)
        top.addWidget(self.browse_dir_btn)
        layout.addLayout(top)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(40)
        layout.addWidget(self.log)

        return group

    # =========================
    # STATUS HELPERS
    # =========================

    def log_message(self, message):
        stamp = time.strftime("%H:%M:%S")
        self.log.append(f"[{stamp}] {message}")
        QApplication.processEvents()

    def set_status(self, label, text, state):
        label.setText(text)
        label.setProperty("status", state)
        label.style().unpolish(label)
        label.style().polish(label)

    def set_running_state(self, running):
        self.start.setEnabled(not running)
        self.connect_btn.setEnabled(not running)
        self.abort.setEnabled(running)
        self.save_btn.setEnabled((not running) and bool(self.results))
        self.browse_dir_btn.setEnabled(not running)

    def update_sweep_time_estimate(self):
        if not hasattr(self, "sweep_time_label"):
            return

        # Approximate per-point time includes user delay plus VISA write/read
        # overhead observed in this style of point-by-point sweep.
        estimated_seconds = self.points.value() * (self.point_delay.value() + 0.07)
        self.sweep_time_label.setText(
            f"Estimated scan time: {estimated_seconds:.1f} s per pixel/loop"
        )

    def refresh_startup_layout(self):
        self.build_pixels()
        self.updateGeometry()
        self.layout().activate()

    def connect_instruments(self):
        self.log_message("Connecting instruments...")
        keithley_ok, relay_ok = self.inst.connect_all(self.log_message)
        self.set_status(
            self.keithley_status,
            "Keithley: connected" if keithley_ok else "Keithley: offline",
            "ok" if keithley_ok else "bad",
        )
        self.set_status(
            self.relay_status,
            "Relay: connected" if relay_ok else "Relay: offline",
            "ok" if relay_ok else "bad",
        )

    def choose_output_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose TXT Save Folder",
            self.output_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if directory:
            self.output_dir = directory
            self.output_dir_field.setText(directory)
            self.log_message(f"TXT save folder set to {directory}")

    # =========================
    # PIXELS
    # =========================

    def build_pixels(self):
        if not hasattr(self, "pixel_grid"):
            return

        for i in reversed(range(self.pixel_grid.count())):
            w = self.pixel_grid.itemAt(i).widget()
            if w:
                w.setParent(None)

        self.checks = []
        self.areas = []

        pixel_mode = self.pixel_mode.currentText()
        labels = active_pixel_labels(pixel_mode)
        area_default = default_pixel_area(pixel_mode)

        headers = [
            ("Pixel", 0),
            ("Area (cm^2)", 1),
            ("Pixel", 3),
            ("Area (cm^2)", 4),
        ]

        for text, col in headers:
            header = QLabel(text)
            header.setStyleSheet("font-weight: 700; color: #52606d;")
            self.pixel_grid.addWidget(header, 0, col)

        # Center live-measurement label
        self.pixel_grid.addWidget(self.current_pixel_label, 0, 2)
        self.pixel_grid.setRowMinimumHeight(0, 18)

        visible_rows = (len(labels) + 1) // 2
        for row in range(1, 7):
            self.pixel_grid.setRowMinimumHeight(row, 32 if row <= visible_rows else 0)

        if hasattr(self, "pixel_group"):
            self.pixel_group.setMinimumHeight(200 if len(labels) <= 6 else 390)

        for i, lab in enumerate(labels):
            cb = QCheckBox(lab)
            cb.setMinimumWidth(58)
            cb.setFixedHeight(32)
            cb.setChecked(True)

            area = NoWheelDoubleSpinBox()
            area.setMinimumWidth(120)
            area.setFixedHeight(32)
            area.setRange(0.0001, 100)
            area.setDecimals(4)
            area.setValue(area_default)
            area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            self.checks.append(cb)
            self.areas.append(area)

            row = (i // 2) + 1
            col = 0 if (i % 2 == 0) else 3
            self.pixel_grid.addWidget(cb, row, col)
            self.pixel_grid.addWidget(area, row, col + 1)

        self.pixel_grid.invalidate()
        self.updateGeometry()

    # =========================
    # MEASUREMENT
    # =========================

    def run_measurement(self):
        self.abort_flag = False
        self.results = []
        self.table.setRowCount(0)
        self.plot.clear()
        self.clear_plot_legends()
        self.apply_default_plot_range()

        if not self.inst.keithley or not self.inst.relay:
            self.log_message("ERROR: instruments are not connected")
            return

        selected = []
        for i, checkbox in enumerate(self.checks):
            if checkbox.isChecked():
                pixel = checkbox.text()
                selected.append((pixel, PIXEL_TO_RELAY_CHANNEL[pixel], self.areas[i].value()))
        if not selected:
            self.log_message("ERROR: select at least one pixel")
            return

        keithley = self.inst.keithley
        relay = self.inst.relay
        base_v0 = self.v0.value()
        base_v1 = self.v1.value()
        reverse = self.dir.currentText() == "Reverse"
        pin = self.pin.value()
        compliance_a = self.compliance_ma.value() / 1000
        point_delay_s = self.point_delay.value()
        loops = self.loops.value()
        points = self.points.value()
        self.reset_plot_legends(selected, loops)

        self.set_running_state(True)

        measurement_error = False

        try:
            init_keithley(keithley, compliance_a=compliance_a, logger=self.log_message)
            self.log_message(f"Keithley current compliance set to {compliance_a:.6f} A")

            for loop_idx in range(loops):
                if self.abort_flag:
                    break

                self.log_message(f"Starting loop {loop_idx + 1} of {loops}")

                for pixel, ch, area in selected:
                    if self.abort_flag:
                        break

                    relay_token = numato_relay_token(ch)
                    self.log_message(f"Measuring pixel {pixel} on relay channel {ch} ({relay_token})")
                    self.current_pixel_label.setText(f"Measuring pixel: {pixel}")
                    QApplication.processEvents()
                    keithley_output_safe(keithley)
                    all_pixels_disconnect(relay)
                    time.sleep(RELAY_SETTLE_S)
                    connect_pixel(relay, ch)
                    time.sleep(RELAY_SETTLE_S)
                    keithley_output_enable(keithley, logger=self.log_message)

                    sweep_start, sweep_end = (base_v1, base_v0) if reverse else (base_v0, base_v1)
                    V = np.linspace(sweep_start, sweep_end, points)
                    V_keithley = []
                    I = []
                    self.log_message(
                        f"Sweep {pixel} device voltage: {sweep_start:.3f} V -> {sweep_end:.3f} V "
                        f"({points} points, {'reverse' if reverse else 'forward'})"
                    )

                    for point_idx, v in enumerate(V):
                        if self.abort_flag:
                            break
                        current, raw, keithley_v = keithley_read_current(keithley, v, point_delay_s)
                        V_keithley.append(keithley_v)
                        if point_idx == 0:
                            self.log_message(f"First raw Keithley current response for {pixel}: {raw}")
                        if point_idx in {0, len(V) // 2, len(V) - 1}:
                            try:
                                source_check = keithley_source_voltage(keithley)
                                self.log_message(
                                    f"{pixel} source check point {point_idx + 1}: "
                                    f"device {v:.4f} V, Keithley command {keithley_v:.4f} V, "
                                    f"Keithley setpoint {source_check:.4f} V"
                                )
                            except Exception as e:
                                self.log_message(f"WARNING: could not query Keithley source voltage: {e}")
                        I.append(current)
                        QApplication.processEvents()

                    keithley_output_safe(keithley)
                    numato_command(relay, f"relay off {numato_relay_token(ch)}")
                    time.sleep(RELAY_SETTLE_S)

                    if self.abort_flag:
                        break

                    I = np.asarray(I, dtype=float)
                    V_keithley = np.asarray(V_keithley, dtype=float)
                    self.log_current_outliers(pixel, V, I, area)
                    fault = check_fault(I)
                    if fault:
                        self.add_result_row(pixel, area, None, fault, loop_idx + 1)
                        self.log_message(f"Pixel {pixel} flagged as {fault}")
                        continue

                    metrics = extract_parameters(V, I, area, pin)
                    J = (I / area) * 1000
                    self.plot.plot(V, J, pen=self.curve_pen(ch, loop_idx + 1))

                    record = {
                        "pixel": pixel,
                        "channel": ch,
                        "loop": loop_idx + 1,
                        "area_cm2": area,
                        "pin_mw_cm2": pin,
                        "voltage_v": V.tolist(),
                        "keithley_voltage_v": V_keithley.tolist(),
                        "current_a": I.tolist(),
                        **metrics,
                    }
                    self.results.append(record)
                    self.add_result_row(pixel, area, metrics, "OK", loop_idx + 1)
                    self.log_message(
                        f"Pixel {pixel}: Voc={metrics['Voc']:.3f} V, "
                        f"Jsc={metrics['Jsc']:.3f} mA/cm^2, "
                        f"PCE={metrics['PCE']:.2f}%"
                    )

        except Exception as e:
            measurement_error = True
            self.log_message(f"ERROR: measurement stopped: {e}")
        finally:
            try:
                keithley_output_safe(keithley)
                all_pixels_disconnect(relay)
            except Exception:
                pass
            self.current_pixel_label.setText("Measuring pixel: --")
            self.set_running_state(False)
            if self.abort_flag:
                self.log_message("Sweep aborted")
            elif measurement_error:
                self.log_message("Sweep ended with an error")
            else:
                self.log_message("Sweep complete")
            if self.auto_save.isChecked() and self.results:
                self.save_results(auto=True)

    def log_current_outliers(self, pixel, V, I, area):
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
            self.log_message(
                f"WARNING: {pixel} current-density spike at {V[peak_idx]:.3f} V: "
                f"{peak:.2f} mA/cm^2 vs median {median:.2f} mA/cm^2"
            )

    def add_result_row(self, pixel, area, metrics, status, loop_idx=None):
        r = self.table.rowCount()
        self.table.insertRow(r)

        values = [
            f"L{loop_idx}" if loop_idx is not None else "--",
            pixel,
            f"{area:.4f}",
        ]

        if metrics:
            values.extend([
                self.format_metric(metrics["Voc"], 3),
                self.format_metric(metrics["Jsc"], 3),
                self.format_metric(metrics["FF"], 3),
                self.format_metric(metrics["PCE"], 3),
                self.format_metric(metrics["Vmpp"], 3),
                self.format_metric(metrics["Jmpp"], 3),
                self.format_metric(metrics["Pmax"], 3),
            ])
        else:
            values.extend(["--", "--", "--", "--", "--", "--", "--"])

        values.append(status)

        for col, value in enumerate(values):
            item = QTableWidgetItem(value)

            if col > 0:
                item.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(r, col, item)

        # Force visual refresh
        self.table.viewport().update()
        QApplication.processEvents()

    @staticmethod
    def format_metric(value, decimals):
        if value is None or not np.isfinite(value):
            return "--"
        return f"{value:.{decimals}f}"

    @staticmethod
    def safe_filename_part(text):
        allowed = []
        for ch in text:
            if ch.isalnum() or ch in ("-", "_"):
                allowed.append(ch)
            elif ch in (" ", ".", "/"):
                allowed.append("_")
        return "".join(allowed).strip("_") or "solar_iv_data"

    def build_daily_output_dir(self):
        date_folder = time.strftime("%Y%m%d")
        path = os.path.abspath(os.path.join(self.output_dir, date_folder))
        os.makedirs(path, exist_ok=True)
        return path

    def build_txt_path(self, row, timestamp):
        basename = os.path.basename(self.file.text().strip() or "solar_iv_data")
        root, ext = os.path.splitext(basename)
        if ext:
            basename = root

        basename = self.safe_filename_part(basename)
        pixel = self.safe_filename_part(str(row["pixel"]))
        loop = int(row.get("loop", 1))
        filename = f"{basename}_pixel_{pixel}_loop_{loop}_{timestamp}.txt"
        return os.path.join(self.build_daily_output_dir(), filename)

    def build_results_table_path(self, timestamp):
        basename = os.path.basename(self.file.text().strip() or "solar_iv_data")
        root, ext = os.path.splitext(basename)

        if ext:
            basename = root

        basename = self.safe_filename_part(basename)

        filename = f"{basename}_results_{timestamp}.txt"

        return os.path.join(self.build_daily_output_dir(), filename)


    def save_results_table(self, timestamp):
        path = self.build_results_table_path(timestamp)
        rows = sorted(
            self.results,
            key=lambda row: (int(row.get("loop", 1)), int(row.get("channel", 0))),
        )

        with open(path, "w") as f:
            f.write(
                "# loop\tpixel\tarea_cm2\tVoc_V\tJsc_mA_cm2\tFF\t"
                "PCE_percent\tVmpp_V\tJmp_mA_cm2\tPmax_mW_cm2\tstatus\n"
            )

            for row in rows:
                f.write(
                    f"{int(row.get('loop', 1))}\t"
                    f"{row['pixel']}\t"
                    f"{row['area_cm2']:.8g}\t"
                    f"{row['Voc']:.8g}\t"
                    f"{row['Jsc']:.8g}\t"
                    f"{row['FF']:.8g}\t"
                    f"{row['PCE']:.8g}\t"
                    f"{row['Vmpp']:.8g}\t"
                    f"{row['Jmpp']:.8g}\t"
                    f"{row['Pmax']:.8g}\t"
                    "OK\n"
                )

        return path

    def save_results(self, auto=False):
        if not self.results:
            self.log_message("No results to save")
            return

        timestamp = time.strftime("%H%M%S")
        saved_paths = []

        try:
            for row in self.results:
                path = self.build_txt_path(row, timestamp)
                V = np.asarray(row["voltage_v"], dtype=float)
                I = np.asarray(row["current_a"], dtype=float)
                J = (I / row["area_cm2"]) * 1000

                with open(path, "w") as f:
                    f.write("# voltage_v\tcurrent_density_mA_cm2\n")
                    for voltage, current_density in zip(V, J):
                        f.write(f"{voltage:.8g}\t{current_density:.8g}\n")
                saved_paths.append(path)

            self.save_results_table(timestamp)

            mode = "Auto-saved" if auto else "Saved"
            folder = self.build_daily_output_dir()

            self.log_message(
                f"{mode} {len(saved_paths)} JV text file(s) and "
                f"1 results table file to {folder}"
            )
        except Exception as e:
            self.log_message(f"ERROR: could not save TXT files: {e}")

    def abort_measurement(self):
        self.abort_flag = True
        self.log_message("Abort requested")


# =========================
# RUN
# =========================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pg.setConfigOptions(antialias=True)
    w = GUI()
    w.show()
    sys.exit(app.exec_())
