"""
Main window for the Multiplex Solar Simulator IV characterization app.

Responsibilities:
  - GUI Layout: Builds the control panels, J-V plot manager, and results table.
  - Worker Coordination: Instantiates, starts, and aborts the asynchronous 
    MeasurementWorker QThread.
  - Signal Handling: Receives measurement streams from the background thread
    to update plots, log messages, and output tables safely.
"""
import html
import os
import time

import numpy as np
import pyqtgraph as pg

from PyQt5.QtCore import Qt, QTimer, QEvent, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QTextCursor, QColor, QBrush
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
from gui.style import get_theme, get_theme_colors


class GUI(QWidget):
    def __init__(self):
        super().__init__()
        self.is_dark_mode = False
        self._shadow_widgets = []
        self._role_colored_items = []  # [(QTableWidgetItem, role), ...] for theme refresh

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
        self.setStyleSheet(get_theme(self.is_dark_mode))

    def build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(10)

        # 1. Header stays visible at the top
        main.addWidget(self.build_header())

        # 2. Main Tab Widget
        self.tabs = QTabWidget()
        main.addWidget(self.tabs, 1)

        # TAB 1: CONFIGURATION
        config_tab = QWidget()
        config_layout = QHBoxLayout(config_tab)
        config_layout.setSpacing(15)
        config_layout.addWidget(self.build_sweep_panel(), 1)
        config_layout.addWidget(self.build_pixel_panel(), 2)
        self.tabs.addTab(config_tab, "1. CONFIGURATION")

        # TAB 2: LIVE SWEEP
        live_tab = QWidget()
        live_layout = QHBoxLayout(live_tab)
        live_layout.setSpacing(15)
        live_layout.addWidget(self.build_plot_panel(), 3)
        live_layout.addWidget(self.build_live_hud(), 1)
        self.tabs.addTab(live_tab, "2. LIVE SWEEP")

        # TAB 3: RESULTS GALLERY
        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        results_layout.addWidget(self.build_results_panel())
        self.tabs.addTab(results_tab, "3. RESULTS GALLERY")

        # TAB 4: SYSTEM LOGS
        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.addWidget(self.build_log_panel())
        self.tabs.addTab(logs_tab, "4. SYSTEM LOGS")

        # 3. Global Footer Strip
        self.footer = QFrame()
        self.footer.setObjectName("FooterStrip")
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(16, 12, 16, 12)

        lbl_title = QLabel("SWEEP PROGRESS:")
        lbl_title.setObjectName("AccentLabel")
        footer_layout.addWidget(lbl_title)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        footer_layout.addWidget(self.progress_bar, 1) # Stretch = 1

        self.progress_pct = QLabel("0%")
        self.progress_pct.setObjectName("MainLabel")
        footer_layout.addWidget(self.progress_pct)

        # Vertical divider line
        divider = QFrame()
        divider.setObjectName("VDivider")
        divider.setFrameShape(QFrame.VLine)
        footer_layout.addWidget(divider)

        self.progress_txt = QLabel("Ready")
        self.progress_txt.setObjectName("DimLabel")
        footer_layout.addWidget(self.progress_txt)

        self.footer.setVisible(False)
        self.add_panel_shadow(self.footer)
        main.addWidget(self.footer)

    def build_header(self):
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(64)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignVCenter)

        # Brand Title
        self.brand_title = QLabel("MULTIPLEX SIM")
        self.brand_title.setObjectName("BrandTitle")
        layout.addWidget(self.brand_title)
        
        layout.addSpacing(10)

        # Keithley LED
        self.keithley_led = QLabel()
        self.keithley_led.setObjectName("StatusLED")
        self.keithley_led.setProperty("status", "idle")
        layout.addWidget(self.keithley_led)
        
        self.keithley_lbl = QLabel("KEITHLEY 2460")
        self.keithley_lbl.setObjectName("StatusLabel")
        self.keithley_lbl.setProperty("status", "idle")
        layout.addWidget(self.keithley_lbl)

        layout.addSpacing(5)

        # Relay LED
        self.relay_led = QLabel()
        self.relay_led.setObjectName("StatusLED")
        self.relay_led.setProperty("status", "idle")
        layout.addWidget(self.relay_led)
        
        self.relay_lbl = QLabel("RELAY MATRIX")
        self.relay_lbl.setObjectName("StatusLabel")
        self.relay_lbl.setProperty("status", "idle")
        layout.addWidget(self.relay_lbl)

        layout.addSpacing(15)

        # Compact Connection Button
        self.connect_btn = QPushButton("Connect Instruments")
        self.connect_btn.setMinimumHeight(32)
        self.connect_btn.clicked.connect(self.connect_instruments)
        layout.addWidget(self.connect_btn)

        layout.addStretch(1)

        # Right Side Inputs (Sample ID & Browse)
        self.sample_lbl = QLabel("Sample ID:")
        self.sample_lbl.setObjectName("DimLabel")
        layout.addWidget(self.sample_lbl)

        self.file = QLineEdit("Sample_Batch_01")
        self.file.setFixedWidth(180)
        self.file.setMinimumHeight(32)
        layout.addWidget(self.file)

        self.browse_dir_btn = QPushButton("Browse...")
        self.browse_dir_btn.setObjectName("PrimaryButton")
        self.browse_dir_btn.setMinimumHeight(32)
        self.browse_dir_btn.clicked.connect(self.choose_output_dir)
        layout.addWidget(self.browse_dir_btn)

        # Theme Toggle
        self.theme_btn = QPushButton("☀️" if self.is_dark_mode else "🌙")
        self.theme_btn.setObjectName("ThemeButton")
        self.theme_btn.setFixedSize(36, 36)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_btn)

        return header

    def build_pixel_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header Row
        header_row = QHBoxLayout()
        title_lbl = QLabel("PIXEL MATRIX")
        title_lbl.setObjectName("PanelTitle")
        header_row.addWidget(title_lbl)
        
        header_row.addStretch(1)
        
        self.pixel_mode = NoWheelComboBox()
        self.pixel_mode.setFixedWidth(120)
        self.pixel_mode.addItems(["6 Pixels", "12 Pixels"])
        self.pixel_mode.currentIndexChanged.connect(self.build_pixels)
        header_row.addWidget(self.pixel_mode)
        layout.addLayout(header_row)

        # Divider line
        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        # Grid Area
        self.pixel_grid = QGridLayout()
        self.pixel_grid.setSpacing(10)
        self.pixel_grid.setAlignment(Qt.AlignTop)

        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent; border: none;")
        grid_widget.setLayout(self.pixel_grid)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)

        # Track the viewport so the grid can reflow its column count as the
        # panel resizes [Need to be modified]
        self._pixel_scroll_viewport = scroll.viewport()
        self._pixel_scroll_viewport.installEventFilter(self)
        self._pixel_card_min_width = 160
        self._pixel_grid_cols = 3

        self.checks = []
        self.areas = []
        self.build_pixels()

        # Keep reference so status updater doesn't crash
        self.current_pixel_label = QLabel()
        self.current_pixel_label.setVisible(False)

        self.add_panel_shadow(panel)
        return panel

    def build_sweep_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(0)

        # Header Title
        title_lbl = QLabel("SWEEP SETUP")
        title_lbl.setObjectName("PanelTitle")
        title_lbl.setStyleSheet("padding-bottom: 8px;")
        layout.addWidget(title_lbl)

        # Divider line under header
        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        # Inputs
        self.v0 = NoWheelDoubleSpinBox()
        self.v0.setRange(-5, 5)
        self.v0.setDecimals(2)
        self.v0.setValue(-0.2)

        self.v1 = NoWheelDoubleSpinBox()
        self.v1.setRange(-5, 5)
        self.v1.setDecimals(2)
        self.v1.setValue(1.3)

        self.points = NoWheelSpinBox()
        self.points.setRange(2, 2000)
        self.points.setValue(100)

        self.dir = NoWheelComboBox()
        self.dir.addItems(["Forward", "Reverse"])
        self.dir.setCurrentText("Reverse")

        self.loops = NoWheelSpinBox()
        self.loops.setRange(1, 20)
        self.loops.setValue(1)

        self.point_delay = NoWheelDoubleSpinBox()
        self.point_delay.setRange(0.001, 10)
        self.point_delay.setDecimals(2)
        self.point_delay.setValue(0.01)

        self.compliance_ma = NoWheelDoubleSpinBox()
        self.compliance_ma.setRange(0.001, 1000)
        self.compliance_ma.setDecimals(0)
        self.compliance_ma.setValue(KEITHLEY_DEFAULT_COMPLIANCE_A * 1000)

        self.pin = NoWheelDoubleSpinBox()
        self.pin.setRange(0.001, 5000)
        self.pin.setDecimals(0)
        self.pin.setValue(100.0)

        # Helper to construct flat rows with fine bottom borders
        def make_row(label_text, widget):
            row = QFrame()
            row.setObjectName("FormRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 8, 0, 8)
            
            lbl = QLabel(label_text)
            lbl.setObjectName("DimLabel")

            row_layout.addWidget(lbl)
            row_layout.addStretch(1)
            row_layout.addWidget(widget)
            return row

        layout.addWidget(make_row("Start Voltage (V)", self.v0))
        layout.addWidget(make_row("Stop Voltage (V)", self.v1))
        layout.addWidget(make_row("Step Count", self.points))
        layout.addWidget(make_row("Direction", self.dir))
        layout.addWidget(make_row("Loops", self.loops))
        layout.addWidget(make_row("Point Delay (s)", self.point_delay))
        layout.addWidget(make_row("Compliance (mA)", self.compliance_ma))
        layout.addWidget(make_row("Irradiance (mW/cm²)", self.pin))

        # Sweep duration label
        self.sweep_time_label = QLabel()
        self.sweep_time_label.setObjectName("DimLabel")
        self.sweep_time_label.setStyleSheet("font-size: 11px; margin-top: 10px;")
        layout.addWidget(self.sweep_time_label)
        self.points.valueChanged.connect(self.update_sweep_time_estimate)
        self.point_delay.valueChanged.connect(self.update_sweep_time_estimate)
        self.update_sweep_time_estimate()

        layout.addStretch(1)

        # Main action button
        self.start = QPushButton("INITIALIZE RUN")
        self.start.setObjectName("PrimaryButton")
        self.start.setMinimumHeight(44)
        self.start.clicked.connect(self.run_measurement)
        layout.addWidget(self.start)

        # Keep unreferenced hidden buttons so current methods don't crash
        self.abort = QPushButton()
        self.abort.setVisible(False)
        self.save_btn = QPushButton()
        self.save_btn.setVisible(False)
        self.auto_save = QCheckBox()
        self.auto_save.setChecked(True)
        self.auto_save.setVisible(False)

        self.add_panel_shadow(panel)
        return panel

    def add_panel_shadow(self, widget):
        """Aesthetic choice that adds a shadow for more eye juicing"""
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(20)
        effect.setXOffset(0)
        effect.setYOffset(4)
        effect.setColor(QColor(0, 0, 0, 90 if self.is_dark_mode else 25))
        widget.setGraphicsEffect(effect)
        self._shadow_widgets.append(widget)

    def build_panel_header(self, layout, title_text):
        """Adds a PanelTitle label + Divider line to a layout, matching the
        '.panel h2' look used across every panel in the HTML mock."""
        title_lbl = QLabel(title_text.upper())
        title_lbl.setObjectName("PanelTitle")
        layout.addWidget(title_lbl)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

    def build_plot_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.build_panel_header(layout, "IV Curves")

        self.plot_manager = PlotManager(
            range_dialog_callback=lambda: self.plot_manager.open_range_dialog(self, self.log_message)
        )
        self.plot = self.plot_manager.widget
        layout.addWidget(self.plot)

        # Sync initial plot colors w/ the active theme.
        colors = get_theme_colors(self.is_dark_mode)
        self.plot.setBackground(colors["bg_panel"])
        self.plot.getAxis("bottom").setPen(pg.mkPen(colors["border"]))
        self.plot.getAxis("left").setPen(pg.mkPen(colors["border"]))
        self.plot.getAxis("bottom").setTextPen(pg.mkPen(colors["text_dim"]))
        self.plot.getAxis("left").setTextPen(pg.mkPen(colors["text_dim"]))

        self.add_panel_shadow(panel)
        return panel

    def build_live_hud(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setMinimumWidth(280)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        active_dot = QLabel("\u25cf")
        active_dot.setObjectName("HudActivePixel")
        header_row.addWidget(active_dot)

        # Pulsing opacity animation :3
        dot_opacity = QGraphicsOpacityEffect(active_dot)
        active_dot.setGraphicsEffect(dot_opacity)
        self._active_dot_pulse = QPropertyAnimation(dot_opacity, b"opacity", self)
        self._active_dot_pulse.setDuration(1500)
        self._active_dot_pulse.setStartValue(1.0)
        self._active_dot_pulse.setKeyValueAt(0.5, 0.25)
        self._active_dot_pulse.setEndValue(1.0)
        self._active_dot_pulse.setEasingCurve(QEasingCurve.InOutSine)
        self._active_dot_pulse.setLoopCount(-1)
        self._active_dot_pulse.start()

        self.hud_active_pixel = QLabel("Active Pixel: --")
        self.hud_active_pixel.setObjectName("PanelTitle")
        header_row.addWidget(self.hud_active_pixel)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        def make_metric(label_text):
            card = QFrame()
            card.setObjectName("MetricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            card_layout.setSpacing(4)
            card_layout.setAlignment(Qt.AlignHCenter)

            lbl_title = QLabel(label_text.upper())
            lbl_title.setObjectName("MetricLabel")
            lbl_title.setAlignment(Qt.AlignHCenter)

            lbl_val = QLabel("--")
            lbl_val.setObjectName("MetricValue")
            lbl_val.setAlignment(Qt.AlignHCenter)

            card_layout.addWidget(lbl_title)
            card_layout.addWidget(lbl_val)
            layout.addWidget(card)
            return lbl_val

        self.hud_voc = make_metric("Voc (V)")
        self.hud_jsc = make_metric("Jsc (mA/cm\u00b2)")
        self.hud_pce = make_metric("PCE (%)")
        self.hud_ff  = make_metric("Fill Factor")

        layout.addStretch()

        # Big Abort button for the Live Tab
        self.hud_abort = QPushButton("ABORT SWEEP")
        self.hud_abort.setObjectName("DangerButton")
        self.hud_abort.setMinimumHeight(50)
        self.hud_abort.clicked.connect(self.abort_measurement)
        self.hud_abort.setEnabled(False)
        layout.addWidget(self.hud_abort)

        self.add_panel_shadow(panel)
        return panel

    def build_results_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.build_panel_header(layout, "Extracted Metrics")

        self.table = QTableWidget()
        self.table.setColumnCount(15)
        self.table.setHorizontalHeaderLabels(
            ["Loop", "Pixel", "Area", "Voc (V)", "Jsc (mA/cm^2)", "FF",
             "PCE (%)", "Vmpp (V)", "Jmp (mA/cm^2)", "Pmax (mW/cm^2)",
             "Rs fit (\u03a9)", "Rsh fit (\u03a9)", "Rs deriv (\u03a9)", "Rsh deriv (\u03a9)",
             "Status"]
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

        self.add_panel_shadow(panel)
        return panel

    def build_log_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.build_panel_header(layout, "System Event Log")

        # 1. Instantiate the log
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        # 2. Build the top control bar
        top = QHBoxLayout()

        save_dir_lbl = QLabel("Save Directory:")
        save_dir_lbl.setObjectName("DimLabel")
        top.addWidget(save_dir_lbl)
        self.output_dir_field = QLineEdit(self.output_dir)
        self.output_dir_field.setReadOnly(True)
        top.addWidget(self.output_dir_field, 1)

        # Export .TXT Button
        self.export_log_btn = QPushButton("Export .TXT")
        self.export_log_btn.clicked.connect(self.export_log_data)
        top.addWidget(self.export_log_btn)

        # Clear Button
        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.log.clear)
        top.addWidget(self.clear_log_btn)
        
        layout.addLayout(top)

        # 3. Add the log widget to the layout last so it sits below the control bar
        layout.addWidget(self.log)

        self.add_panel_shadow(panel)
        return panel

    # --- UI Status & Logging Helpers ---

    def log_message(self, message):
        stamp = time.strftime("%H:%M:%S")
        colors = get_theme_colors(self.is_dark_mode)

        prefix, sep, rest = message.partition(": ")
        prefix_key = prefix.strip().upper()

        severity_colors = {
            "OK": (colors["success"], colors["text_main"]),
            "WARNING": (colors["warning"], colors["warning"]),
            "ERROR": (colors["error"], colors["error"]),
        }

        ts_html = f'<span style="color:{colors["text_dim"]};">[{stamp}]</span>'

        if sep and prefix_key in severity_colors:
            prefix_color, text_color = severity_colors[prefix_key]
            body_html = (
                f'<span style="color:{prefix_color}; font-weight:bold;">{html.escape(prefix)}:</span> '
                f'<span style="color:{text_color};">{html.escape(rest)}</span>'
            )
        else:
            body_html = f'<span style="color:{colors["text_main"]};">{html.escape(message)}</span>'

        self.log.append(f"{ts_html} {body_html}")
        self.log.moveCursor(QTextCursor.End) # Auto-scroll
        QApplication.processEvents()

    def set_status_led(self, led, label, state):
        """Updates the status property of LEDs and Labels and repolishes them."""
        led.setProperty("status", state)
        label.setProperty("status", state)
        
        # Force Qt to reload stylesheet
        led.style().unpolish(led)
        led.style().polish(led)
        label.style().unpolish(label)
        label.style().polish(label)

        self._refresh_led_glow(led)

    def _refresh_led_glow(self, led):
        """LED glowwer, similar to shadow function; simply visual"""
        state = led.property("status")
        colors = get_theme_colors(self.is_dark_mode)
        glow_color = {"ok": colors["success"], "bad": colors["error"]}.get(state)

        if glow_color:
            effect = led.graphicsEffect()
            if not isinstance(effect, QGraphicsDropShadowEffect):
                effect = QGraphicsDropShadowEffect(led)
                effect.setBlurRadius(14)
                effect.setXOffset(0)
                effect.setYOffset(0)
                led.setGraphicsEffect(effect)
            effect.setColor(QColor(glow_color))
        else:
            led.setGraphicsEffect(None)

    def set_running_state(self, running):
        self.start.setEnabled(not running)
        self.connect_btn.setEnabled(not running)
        self.abort.setEnabled(running)
        self.hud_abort.setEnabled(running)
        self.save_btn.setEnabled((not running) and bool(self.results))
        self.browse_dir_btn.setEnabled(not running)
        
        # Show footer strip only when running
        self.footer.setVisible(running)
        if running:
            self.progress_bar.setValue(0)
            self.progress_pct.setText("0%")
            self.progress_txt.setText("Initializing hardware...")
    
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
        self.recompute_pixel_grid_columns()
        self.build_pixels()
        self.updateGeometry()
        self.layout().activate()

    def connect_instruments(self):
        self.log_message("Connecting instruments...")
        keithley_ok, relay_ok = self.inst.connect_all(self.log_message)
        
        self.set_status_led(self.keithley_led, self.keithley_lbl, "ok" if keithley_ok else "bad")
        self.set_status_led(self.relay_led, self.relay_lbl, "ok" if relay_ok else "bad")

        self.connect_btn.setText("Reconnect")

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

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.Resize
            and hasattr(self, "_pixel_scroll_viewport")
            and obj is self._pixel_scroll_viewport
        ):
            self.recompute_pixel_grid_columns()
        return super().eventFilter(obj, event)

    def recompute_pixel_grid_columns(self):
        """Recomputes how many pixel cards fit per row based on the current panel width"""
        if not hasattr(self, "_pixel_scroll_viewport"):
            return

        spacing = self.pixel_grid.spacing()
        card_w = self._pixel_card_min_width
        available = self._pixel_scroll_viewport.width()
        cols = max(1, (available + spacing) // (card_w + spacing))

        if cols != self._pixel_grid_cols:
            self._pixel_grid_cols = cols
            self.build_pixels()

    def build_pixels(self):
        if not hasattr(self, "pixel_grid"):
            return

        # Clear existing
        for i in reversed(range(self.pixel_grid.count())):
            item = self.pixel_grid.itemAt(i)
            if item.widget():
                item.widget().setParent(None)

        self.checks = []
        self.areas = []

        pixel_mode = self.pixel_mode.currentText()
        labels = active_pixel_labels(pixel_mode)
        area_default = default_pixel_area(pixel_mode)

        cols = getattr(self, "_pixel_grid_cols", 3)
        for i, lab in enumerate(labels):
            card = QFrame()
            card.setObjectName("PixelCard")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(12, 6, 12, 6)
            card_layout.setSpacing(8)

            cb = QCheckBox(lab)
            cb.setStyleSheet("font-weight: bold; border: none; background: transparent;")
            cb.setChecked(True)

            area = NoWheelDoubleSpinBox()
            area.setRange(0.0001, 100)
            area.setDecimals(4)
            area.setValue(area_default)
            area.setStyleSheet("border: none; background: transparent; padding: 0px;")

            card_layout.addWidget(cb)
            card_layout.addStretch(1)
            card_layout.addWidget(area)

            self.checks.append(cb)
            self.areas.append(area)

            row = i // cols
            col = i % cols
            self.pixel_grid.addWidget(card, row, col)

        self.pixel_grid.invalidate()
        self.updateGeometry()
    
    def validate_inputs(self):
        if not self.inst.keithley or not self.inst.relay:
            self.log_message("ERROR: Instruments are not connected.")
            return False
            
        if self.v0.value() == self.v1.value():
            self.log_message("ERROR: Start and Stop voltage cannot be the same.")
            return False
            
        any_checked = any(cb.isChecked() for cb in self.checks)
        if not any_checked:
            self.log_message("ERROR: Please select at least one pixel.")
            return False
            
        return True

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_style()
        
        # Change only the emoji symbol
        self.theme_btn.setText("☀️" if self.is_dark_mode else "🌙")
        
        # Force status widgets to refresh their colors against the new stylesheet
        for w in (self.keithley_led, self.keithley_lbl, self.relay_led, self.relay_lbl):
            w.style().unpolish(w)
            w.style().polish(w)
        
        # Update PyQtGraph colors manually (pyqtgraph isn't QSS-driven)
        colors = get_theme_colors(self.is_dark_mode)
        self.plot_manager.plot.setBackground(colors["bg_panel"])
        self.plot_manager.plot.getAxis("bottom").setPen(pg.mkPen(colors["border"]))
        self.plot_manager.plot.getAxis("left").setPen(pg.mkPen(colors["border"]))
        self.plot_manager.plot.getAxis("bottom").setTextPen(pg.mkPen(colors["text_dim"]))
        self.plot_manager.plot.getAxis("left").setTextPen(pg.mkPen(colors["text_dim"]))

        # Refresh panel drop-shadows for the new theme
        for widget in self._shadow_widgets:
            effect = widget.graphicsEffect()
            if effect is not None:
                effect.setColor(QColor(0, 0, 0, 90 if self.is_dark_mode else 25))

        # Recolor role-based table cells (fit-cells, status) rather than
        # assuming warning/success/error stay identical across themes
        for item, role in self._role_colored_items:
            item.setForeground(QBrush(QColor(colors[role])))

        # Refresh LED glow colors for the new theme
        for led in (self.keithley_led, self.relay_led):
            self._refresh_led_glow(led)
    
    # --- Sweep Execution & Signal Slots ---
    def run_measurement(self):
        if not self.validate_inputs():
            self.tabs.setCurrentIndex(0)
            return

        self.results = []
        self.table.setRowCount(0)
        self._role_colored_items = []
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
        self.worker.progress_update.connect(self._on_progress_update)
        self.tabs.setCurrentIndex(1)
        self.worker.start()

    def _on_pixel_started(self, pixel):
        self.current_pixel_label.setText(f"Measuring pixel: {pixel}")
        self.hud_active_pixel.setText(f"Active Pixel: {pixel}")
        
        # Reset HUD numbers for the new pixel
        for lbl in (self.hud_voc, self.hud_jsc, self.hud_pce, self.hud_ff):
            lbl.setText("--")

    def _on_pixel_result(self, record):
        self.results.append(record)
        V = np.asarray(record["voltage_v"], dtype=float)
        J = np.asarray(record["current_density_ma_cm2"], dtype=float)
        self.plot_manager.plot_curve(V, J, record["channel"], record["loop"])
        metric_keys = (
            "Voc", "Jsc", "Vmpp", "Jmpp", "Pmax", "FF", "PCE",
            "Rs_diode_eq", "Rsh_diode_eq", "Rs_derivative", "Rsh_derivative",
        )
        metrics = {k: record[k] for k in metric_keys}
        self.add_result_row(record["pixel"], record["area_cm2"], metrics, "OK", record["loop"])
        
        # Update the HUD with formatted metrics
        self.hud_voc.setText(self.format_metric(metrics["Voc"], 3))
        self.hud_jsc.setText(self.format_metric(metrics["Jsc"], 2))
        self.hud_pce.setText(self.format_metric(metrics["PCE"], 2))
        self.hud_ff.setText(self.format_metric(metrics["FF"], 2))

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

    def _on_progress_update(self, percent, text):
        self.progress_bar.setValue(percent)
        self.progress_pct.setText(f"{percent}%")
        self.progress_txt.setText(text)

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
                self.format_resistance(metrics.get("Rs_diode_eq")),
                self.format_resistance(metrics.get("Rsh_diode_eq")),
                self.format_resistance(metrics.get("Rs_derivative")),
                self.format_resistance(metrics.get("Rsh_derivative")),
            ])
        else:
            values.extend(["--"] * 11)

        values.append(status)

        # Column indices for the diode-model fit values (Rs fit / Rsh fit).
        FIT_CELL_COLUMNS = {10, 11}

        for col, value in enumerate(values):
            item = QTableWidgetItem(value)

            if col > 0:
                item.setTextAlignment(Qt.AlignCenter)

            if col in FIT_CELL_COLUMNS and value != "--":
                self._apply_role_color(item, "warning")
                font = item.font()
                font.setItalic(True)
                font.setBold(True)
                item.setFont(font)

            if col == self.table.columnCount() - 1:
                # Status column: green for OK, red for any fault string
                self._apply_role_color(item, "success" if value == "OK" else "error")
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.table.setItem(r, col, item)

    def _apply_role_color(self, item, role):
        """Colors a table item by semantic role (warning/success/error)"""
        item.setForeground(QBrush(QColor(get_theme_colors(self.is_dark_mode)[role])))
        self._role_colored_items.append((item, role))

    @staticmethod
    def format_metric(value, decimals):
        if value is None or not np.isfinite(value):
            return "--"
        return f"{value:.{decimals}f}"

    @staticmethod
    def format_resistance(value):
        """
        SI-style formatter for resistances.
        Converts raw ohms into readable k and M suffixes.
        """
        if value is None or not np.isfinite(value):
            return "--"
        
        abs_val = abs(value)
        
        # Millions (Mega-ohms)
        if abs_val >= 1_000_000:
            return f"{value / 1_000_000:.2f} M"
        
        # Thousands (Kilo-ohms)
        elif abs_val >= 1_000:
            # For large Rsh (over 10k), 1 decimal: [e.g. 133.2 k]
            # For small Rs errors (under 10k), 2 decimal: [e.g. 3.29 k]
            if abs_val >= 10_000:
                return f"{value / 1_000:.1f} k"
            return f"{value / 1_000:.2f} k"
        
        # Standard Ohms
        elif abs_val >= 1:
            return f"{value:.2f}"
        
        # Sub-ohm values
        else:
            return f"{value:.3f}"


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

    def export_log_data(self):
        log_text = self.log.toPlainText()
        if not log_text.strip():
            self.log_message("WARNING: Log is empty, nothing to export.")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"System_Log_{timestamp}.txt"
        path = os.path.join(self.output_dir, filename)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(log_text)
            self.log_message(f"OK: Log successfully exported to {path}")
        except Exception as e:
            self.log_message(f"ERROR: Could not export log file: {e}")

