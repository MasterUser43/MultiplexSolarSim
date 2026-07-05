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
                margin-top: 18px;
                padding: 14px 12px 12px 12px;
                font-weight: 700;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
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
                min-height: 36px;
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
        left_panel.setFixedWidth(840)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_layout.addWidget(self.build_pixel_panel())
        left_layout.addWidget(self.build_sweep_panel())
        left_layout.addStretch(1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
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
        group.setFixedHeight(525)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 22, 14, 14)
        layout.setSpacing(16)

        row = QHBoxLayout()
        row.addWidget(QLabel("Array"))
        self.pixel_mode = NoWheelComboBox()
        self.pixel_mode.addItems(["6 pixels", "12 pixels"])
        self.pixel_mode.currentIndexChanged.connect(self.build_pixels)
        row.addWidget(self.pixel_mode, 1)
        layout.addLayout(row)

        self.pixel_grid = QGridLayout()
        self.pixel_grid.setHorizontalSpacing(30)
        self.pixel_grid.setVerticalSpacing(13)
        self.pixel_grid.setColumnMinimumWidth(0, 64)
        self.pixel_grid.setColumnMinimumWidth(1, 260)
        self.pixel_grid.setColumnMinimumWidth(2, 64)
        self.pixel_grid.setColumnMinimumWidth(3, 260)
        layout.addLayout(self.pixel_grid)
        self.checks = []
        self.areas = []
        self.build_pixels()

        return group

    def build_sweep_panel(self):
        group = QGroupBox("Sweep Setup")
        group.setFixedHeight(360)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 22, 14, 14)
        layout.setSpacing(12)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.setColumnMinimumWidth(0, 140)
        form.setColumnMinimumWidth(1, 205)
        form.setColumnMinimumWidth(2, 170)
        form.setColumnMinimumWidth(3, 205)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)

        def add_field(row, col, label_text, widget):
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label.setMinimumWidth(140 if col == 0 else 170)
            form.addWidget(label, row, col)
            form.addWidget(widget, row, col + 1)

        self.v0 = NoWheelDoubleSpinBox()
        self.v0.setMinimumWidth(205)
        self.v0.setMinimumHeight(40)
        self.v0.setRange(-5, 5)
        self.v0.setDecimals(3)
        self.v0.setValue(-0.2)

        self.v1 = NoWheelDoubleSpinBox()
        self.v1.setMinimumWidth(205)
        self.v1.setMinimumHeight(40)
        self.v1.setRange(-5, 5)
        self.v1.setDecimals(3)
        self.v1.setValue(1.2)

        self.points = NoWheelSpinBox()
        self.points.setMinimumWidth(205)
        self.points.setMinimumHeight(40)
        self.points.setRange(2, 2000)
        self.points.setValue(50)

        self.loops = NoWheelSpinBox()
        self.loops.setMinimumWidth(205)
        self.loops.setMinimumHeight(40)
        self.loops.setRange(1, 20)
        self.loops.setValue(1)

        self.pin = NoWheelDoubleSpinBox()
        self.pin.setMinimumWidth(205)
        self.pin.setMinimumHeight(40)
        self.pin.setRange(0.001, 5000)
        self.pin.setDecimals(3)
        self.pin.setValue(100.0)

        self.compliance_ma = NoWheelDoubleSpinBox()
        self.compliance_ma.setMinimumWidth(205)
        self.compliance_ma.setMinimumHeight(40)
        self.compliance_ma.setRange(0.001, 1000)
        self.compliance_ma.setDecimals(3)
        self.compliance_ma.setValue(KEITHLEY_DEFAULT_COMPLIANCE_A * 1000)

        self.point_delay = NoWheelDoubleSpinBox()
        self.point_delay.setMinimumWidth(205)
        self.point_delay.setMinimumHeight(40)
        self.point_delay.setRange(0.001, 10)
        self.point_delay.setDecimals(3)
        self.point_delay.setValue(0.150)

        self.dir = NoWheelComboBox()
        self.dir.setMinimumWidth(205)
        self.dir.setMinimumHeight(40)
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

        self.plot = pg.PlotWidget()
        self.plot.setBackground("#ffffff")
        self.plot.showGrid(x=True, y=True, alpha=0.22)
        self.plot.setLabel("bottom", "Voltage", units="V")
        self.plot.setLabel("left", "Current Density", units="mA/cm^2")
        self.plot.addLegend(offset=(12, 12))
        self.plot.setMinimumHeight(300)
        self.plot.setMaximumHeight(340)
        self.plot.getAxis("bottom").setPen(pg.mkPen("#52606d"))
        self.plot.getAxis("left").setPen(pg.mkPen("#52606d"))
        self.plot.getAxis("bottom").setTextPen(pg.mkPen("#334e68"))
        self.plot.getAxis("left").setTextPen(pg.mkPen("#334e68"))
        layout.addWidget(self.plot)

        return group

    def build_results_panel(self):
        group = QGroupBox("Extracted Metrics")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 18, 12, 12)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            ["Pixel", "Area", "Voc (V)", "Jsc (mA/cm^2)", "Vmpp (V)",
             "Jmpp (mA/cm^2)", "FF", "PCE (%)", "Status"]
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
        top.addWidget(QLabel("Data basename"))
        self.file = QLineEdit("solar_iv_data")
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

        for col, text in enumerate(["Pixel", "Area (cm^2)", "Pixel", "Area (cm^2)"]):
            header = QLabel(text)
            header.setStyleSheet("font-weight: 700; color: #52606d;")
            self.pixel_grid.addWidget(header, 0, col)
        self.pixel_grid.setRowMinimumHeight(0, 30)

        # Reserve the full two-column, six-row footprint even when the
        # six-pixel array is selected. This makes the startup layout match
        # the layout after toggling between array sizes.
        for row in range(1, 7):
            self.pixel_grid.setRowMinimumHeight(row, 44)

        for i, lab in enumerate(labels):
            cb = QCheckBox(lab)
            cb.setMinimumWidth(58)
            cb.setMinimumHeight(36)
            cb.setChecked(True)

            area = NoWheelDoubleSpinBox()
            area.setMinimumWidth(250)
            area.setMinimumHeight(36)
            area.setRange(0.0001, 100)
            area.setDecimals(4)
            area.setValue(area_default)
            area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            self.checks.append(cb)
            self.areas.append(area)

            row = (i // 2) + 1
            col = (i % 2) * 2
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

        # Completely reset results table
        self.table.clearContents()
        self.table.setRowCount(0)

        # Completely reset plot + legend
        self.plot.clear()

        # Remove old legend if it exists
        if hasattr(self.plot.plotItem, "legend") and self.plot.plotItem.legend is not None:
            try:
                self.plot.plotItem.legend.scene().removeItem(self.plot.plotItem.legend)
            except Exception:
                pass
            self.plot.plotItem.legend = None

        self.plot.addLegend(offset=(12, 12))

        # Force GUI refresh
        QApplication.processEvents()

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
                        self.add_result_row(pixel, area, None, fault)
                        self.log_message(f"Pixel {pixel} flagged as {fault}")
                        continue

                    metrics = extract_parameters(V, I, area, pin)
                    J = (I / area) * 1000
                    color = self.pixel_colors[ch % len(self.pixel_colors)]
                    name = f"{pixel} L{loop_idx + 1}" if loops > 1 else pixel
                    self.plot.plot(V, J, pen=pg.mkPen(color=color, width=2), name=name)

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
                    self.add_result_row(pixel, area, metrics, "OK")
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
                self.format_metric(metrics["Vmpp"], 3),
                self.format_metric(metrics["Jmpp"], 3),
                self.format_metric(metrics["FF"], 3),
                self.format_metric(metrics["PCE"], 3),
            ])
        else:
            values.extend(["--", "--", "--", "--", "--", "--"])

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

    def build_results_table_path(self, loop, timestamp):
        basename = os.path.basename(self.file.text().strip() or "solar_iv_data")
        root, ext = os.path.splitext(basename)
        if ext:
            basename = root

        basename = self.safe_filename_part(basename)
        filename = f"{basename}_results_loop_{int(loop)}_{timestamp}.txt"
        return os.path.join(self.build_daily_output_dir(), filename)

    def save_results_tables(self, timestamp):
        saved_paths = []
        loops = sorted({int(row.get("loop", 1)) for row in self.results})

        for loop in loops:
            rows = [row for row in self.results if int(row.get("loop", 1)) == loop]
            path = self.build_results_table_path(loop, timestamp)
            with open(path, "w") as f:
                f.write(
                    "# pixel\tarea_cm2\tVoc_V\tJsc_mA_cm2\tVmpp_V\t"
                    "Jmpp_mA_cm2\tFF\tPCE_percent\tstatus\n"
                )
                for row in rows:
                    f.write(
                        f"{row['pixel']}\t"
                        f"{row['area_cm2']:.8g}\t"
                        f"{row['Voc']:.8g}\t"
                        f"{row['Jsc']:.8g}\t"
                        f"{row['Vmpp']:.8g}\t"
                        f"{row['Jmpp']:.8g}\t"
                        f"{row['FF']:.8g}\t"
                        f"{row['PCE']:.8g}\t"
                        "OK\n"
                    )
            saved_paths.append(path)

        return saved_paths

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

            table_paths = self.save_results_tables(timestamp)
            mode = "Auto-saved" if auto else "Saved"
            folder = self.build_daily_output_dir()
            self.log_message(
                f"{mode} {len(saved_paths)} JV text file(s) and "
                f"{len(table_paths)} results table file(s) to {folder}"
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
