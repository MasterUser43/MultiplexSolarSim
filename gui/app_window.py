"""
Main window (PyQt5) for the Multiplex Solar Simulator J-V characterization app.

Responsibilities:
  - GUI Layout: Builds the control panels, J-V plot manager, and results table.
  - Worker Coordination: Instantiates, starts, and aborts the asynchronous 
    MeasurementWorker QThread.
  - Signal Handling: Receives measurement streams from the background thread
    to update plots, log messages, and output tables safely.
"""
import os
import time

import numpy as np
import pyqtgraph as pg

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import *

from core.instrument_manager import InstrumentManager
from core.measurement import (
    PIXEL_TO_RELAY_CHANNEL,
    active_pixel_labels,
    default_pixel_area,
    MeasurementWorker,
)
from core.exporter import ResultsExporter

from instruments.keithley2460 import KEITHLEY_DEFAULT_COMPLIANCE_A

from gui.custom_widgets import NoWheelSpinBox, NoWheelDoubleSpinBox, NoWheelComboBox
from gui.plot_manager import PlotManager
from gui.style import STYLE_SHEET


class GUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Multiplex Solar Simulator - IV Characterization")
        self.resize(1720, 1200)
        self.setMinimumSize(1650, 1160)
        self.setObjectName("Root")

        self.inst = InstrumentManager()
        self.results = []
        self.output_dir = os.getcwd()
        self.curves = {}
        self.exporter = ResultsExporter(self.output_dir, "Sample", lambda msg: self.log_message(msg))

        self.apply_style()
        self.build_ui()
        QTimer.singleShot(0, self.refresh_startup_layout)

    def apply_style(self):
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet(STYLE_SHEET)

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

        self.plot_manager = PlotManager(
            range_dialog_callback=lambda: self.plot_manager.open_range_dialog(self, self.log_message)
        )
        self.plot = self.plot_manager.widget
        layout.addWidget(self.plot)

        return group

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

    # --- UI Status & Logging Helpers ---

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

    # --- Pixel Grid Configuration ---

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

    # --- Sweep Execution & Signal Slots ---

    def run_measurement(self):
        self.results = []
        self.table.setRowCount(0)
        self.plot_manager.clear_curves()
        self.plot_manager.clear_legends()
        self.plot_manager.apply_default_range()

        if not self.inst.keithley or not self.inst.relay:
            self.log_message("ERROR: instruments are not connected")
            return

        if hasattr(self, "worker") and self.worker.isRunning():
            self.log_message("ERROR: a sweep is already running")
            return

        selected = []
        for i, checkbox in enumerate(self.checks):
            if checkbox.isChecked():
                pixel = checkbox.text()
                selected.append((pixel, PIXEL_TO_RELAY_CHANNEL[pixel], self.areas[i].value()))
        if not selected:
            self.log_message("ERROR: select at least one pixel")
            return

        sweep_params = {
            "v0": self.v0.value(),
            "v1": self.v1.value(),
            "reverse": self.dir.currentText() == "Reverse",
            "pin": self.pin.value(),
            "compliance_a": self.compliance_ma.value() / 1000,
            "point_delay_s": self.point_delay.value(),
            "loops": self.loops.value(),
            "points": self.points.value(),
        }

        self.plot_manager.reset_legends(selected, sweep_params["loops"])
        self.set_running_state(True)

        # Pass the active hardware connections to the background thread.
        # To prevent connection conflicts and crashes, do not command or query
        # the instruments from this GUI thread while the sweep is running.
        self.worker = MeasurementWorker(self.inst.keithley, self.inst.relay, selected, sweep_params)
        self.worker.log.connect(self.log_message)
        self.worker.pixel_started.connect(self._on_pixel_started)
        self.worker.pixel_result.connect(self._on_pixel_result)
        self.worker.pixel_faulted.connect(self._on_pixel_faulted)
        self.worker.finished_sweep.connect(self._on_sweep_finished)
        self.worker.start()

    def _on_pixel_started(self, pixel):
        self.current_pixel_label.setText(f"Measuring pixel: {pixel}")

    def _on_pixel_result(self, record):
        self.results.append(record)
        V = np.asarray(record["voltage_v"], dtype=float)
        J = np.asarray(record["current_density_ma_cm2"], dtype=float)
        self.plot_manager.plot_curve(V, J, record["channel"], record["loop"])
        metrics = {k: record[k] for k in ("Voc", "Jsc", "Vmpp", "Jmpp", "Pmax", "FF", "PCE")}
        self.add_result_row(record["pixel"], record["area_cm2"], metrics, "OK", record["loop"])

    def _on_pixel_faulted(self, pixel, area, fault, loop_number):
        self.add_result_row(pixel, area, None, fault, loop_number)

    def _on_sweep_finished(self, aborted, had_error):
        self.current_pixel_label.setText("Measuring pixel: --")
        self.set_running_state(False)

        if aborted:
            self.log_message("Sweep aborted")
        elif had_error:
            self.log_message("Sweep ended with an error")
        else:
            self.log_message("Sweep complete")

        if self.auto_save.isChecked() and self.results:
            self.save_results(auto=True)

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


    def save_results(self, auto=False):
        # Sync the exporter's config from the live widgets, then delegate
        # all path-building and file-writing to core/exporter.py.
        self.exporter.output_dir = self.output_dir
        self.exporter.sample_name = self.file.text().strip() or "solar_iv_data"
        self.exporter.save_results(self.results, auto=auto)

    def abort_measurement(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.request_abort()
            self.log_message("Abort requested")
