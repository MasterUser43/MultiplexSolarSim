"""
Main window for the Multiplex Solar Simulator IV characterization app.

Responsibilities:
  - GUI Layout: Builds the control panels, J-V plot manager, and results table.
  - Worker Coordination: Instantiates, starts, and aborts the asynchronous 
    MeasurementWorker QThread.
  - Signal Handling: Receives measurement streams from the background thread
    to update plots, log messages, and output tables safely.
"""
import os
import sys
import time

import numpy as np
import pyqtgraph as pg

from PyQt5.QtCore import Qt, QTimer, QEvent, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QAbstractAnimation
from PyQt5.QtGui import QFont, QTextCursor, QColor, QBrush, QTextCharFormat, QFontMetrics, QTextFormat
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

from gui.custom_widgets import NoWheelSpinBox, NoWheelDoubleSpinBox, NoWheelComboBox, RichTextHeaderView, SafeTabBar
from gui.plot_manager import PlotManager
from gui.style import get_theme, get_theme_colors


class GUI(QWidget):
    def __init__(self):
        super().__init__()
        self.is_dark_mode = False
        self._shadow_widgets = []

        # Debounces pixel-grid rebuilds triggered by panel resize.
        self._pixel_reflow_timer = QTimer(self)
        self._pixel_reflow_timer.setSingleShot(True)
        self._pixel_reflow_timer.timeout.connect(self.build_pixels)
        self._role_colored_items = []  # [(QTableWidgetItem, role), ...] for theme refresh

        self.setWindowTitle("Multiplex Solar Simulator - IV Characterization")
        self.resize(1720, 1200)
        self.setMinimumSize(1650, 1160)
        self.setObjectName("Root")

        self.inst = InstrumentManager()
        self.results = []
        self.output_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
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
        self.tabs.setTabBar(SafeTabBar(self.tabs))
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        self.tabs.tabBar().setExpanding(False)
        main.addWidget(self.tabs, 1)

        # TAB 1: CONFIGURATION
        config_tab = QWidget()
        config_layout = QHBoxLayout(config_tab)
        config_layout.setSpacing(15)
        config_layout.addWidget(self.build_sweep_panel(), 1)
        config_layout.addWidget(self.build_pixel_panel(), 2)
        self.tabs.addTab(config_tab, "1. CONFIG")

        # TAB 2: LIVE SWEEP
        live_tab = QWidget()
        live_layout = QHBoxLayout(live_tab)
        live_layout.setSpacing(15)
        live_layout.addWidget(self.build_plot_panel(), 3)
        live_layout.addWidget(self.build_live_hud(), 1)
        self.tabs.addTab(live_tab, "2. SWEEP")

        # TAB 3: RESULTS GALLERY
        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        results_layout.addWidget(self.build_results_panel())
        self.tabs.addTab(results_tab, "3. RESULTS")

        # TAB 4: SYSTEM LOGS
        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.addWidget(self.build_log_panel())
        self.tabs.addTab(logs_tab, "4. LOGS")

        # Fade + slight slide-up on tab switch
        self.tabs.currentChanged.connect(self._animate_tab_switch)

        # 3. Global Footer Strip
        self.footer = QFrame()
        self.footer.setObjectName("FooterStrip")
        self.footer.setAttribute(Qt.WA_StyledBackground, True)
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
        header.setFixedHeight(76)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignVCenter)

        # Brand Title
        self.brand_title = QLabel("MULTIPLEX SIM")
        self.brand_title.setObjectName("BrandTitle")
        self.brand_title.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        brand_font = QFont(self.font())
        brand_font.setPointSize(14)
        brand_font.setBold(True)
        self.brand_title.setMinimumWidth(QFontMetrics(brand_font).horizontalAdvance("MULTIPLEX SIM") + 16)
        layout.addWidget(self.brand_title)
        
        layout.addSpacing(10)

        # Keithley LED
        self.keithley_led = QLabel()
        self.keithley_led.setObjectName("StatusLED")
        self.keithley_led.setProperty("status", "idle")
        layout.addWidget(self.keithley_led)
        
        self.keithley_lbl = QLabel("KEITHLEY\n2460")
        self.keithley_lbl.setObjectName("StatusLabel")
        self.keithley_lbl.setProperty("status", "idle")
        self.keithley_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.keithley_lbl)

        layout.addSpacing(5)

        # Relay LED
        self.relay_led = QLabel()
        self.relay_led.setObjectName("StatusLED")
        self.relay_led.setProperty("status", "idle")
        layout.addWidget(self.relay_led)
        
        self.relay_lbl = QLabel("RELAY\nMATRIX")
        self.relay_lbl.setObjectName("StatusLabel")
        self.relay_lbl.setProperty("status", "idle")
        self.relay_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.relay_lbl)

        layout.addSpacing(15)

        # Compact Connection Button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setMinimumHeight(32)
        self.connect_btn.clicked.connect(self.connect_instruments)
        layout.addWidget(self.connect_btn)

        layout.addStretch(1)

        # Right Side Inputs (Sample ID & Browse)
        self.sample_lbl = QLabel("Sample ID:")
        self.sample_lbl.setObjectName("DimLabel")
        layout.addWidget(self.sample_lbl)

        self.file = QLineEdit("Sample_Batch_01")
        self.file.setMinimumWidth(220)
        self.file.setMaximumWidth(340)
        self.file.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
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
        panel.setAttribute(Qt.WA_StyledBackground, True)
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
        self.pixel_mode.setFixedWidth(150)
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
        self.pixel_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.pixel_grid_widget = QWidget()
        self.pixel_grid_widget.setStyleSheet("background: transparent; border: none;")
        self.pixel_grid_widget.setLayout(self.pixel_grid)
        self.pixel_grid_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        layout.addWidget(self.pixel_grid_widget)
        layout.addStretch(1)

        # Widget track so the grid can reflow its column count as panel resizes
        self.pixel_grid_widget.installEventFilter(self)
        self._pixel_card_min_width = 225
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
        panel.setAttribute(Qt.WA_StyledBackground, True)
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

            widget.setFixedWidth(140)

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
        title_lbl.setObjectName("PanelTitleLarge")
        layout.addWidget(title_lbl)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

    def build_plot_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.plot_manager = PlotManager(
            range_dialog_callback=lambda: self.plot_manager.open_range_dialog(self, self.log_message)
        )
        self.plot = self.plot_manager.widget
        layout.addWidget(self.plot, 1)

        # Small utility row under the plot
        tools_row = QHBoxLayout()
        tools_row.setSpacing(8)

        reset_view_btn = QPushButton("Reset View")
        reset_view_btn.clicked.connect(self.plot_manager.apply_default_range)
        tools_row.addWidget(reset_view_btn)

        set_range_btn = QPushButton("Set Range...")
        set_range_btn.clicked.connect(
            lambda: self.plot_manager.open_range_dialog(self, self.log_message)
        )
        tools_row.addWidget(set_range_btn)

        export_png_btn = QPushButton("Export PNG")
        export_png_btn.clicked.connect(self.export_plot_png)
        tools_row.addWidget(export_png_btn)

        tools_row.addStretch(1)
        layout.addLayout(tools_row)

        # Sync initial plot colors w/ the active theme
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
        panel.setAttribute(Qt.WA_StyledBackground, True)
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

        self.hud_active_pixel = QLabel("Latest Pixel: --")
        self.hud_active_pixel.setObjectName("PanelTitleLarge")
        header_row.addWidget(self.hud_active_pixel)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        def make_metric(label_html):
            card = QFrame()
            card.setObjectName("MetricCard")
            card.setAttribute(Qt.WA_StyledBackground, True)
            card.setMinimumHeight(150)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            card_layout.setSpacing(6)
            card_layout.setAlignment(Qt.AlignHCenter)

            # label_html carries its own casing/subscripts
            lbl_title = QLabel(label_html)
            lbl_title.setObjectName("MetricLabel")
            lbl_title.setAlignment(Qt.AlignHCenter)

            lbl_val = QLabel("--")
            lbl_val.setObjectName("MetricValue")
            lbl_val.setAlignment(Qt.AlignHCenter)

            card_layout.addWidget(lbl_title)
            card_layout.addWidget(lbl_val)
            layout.addWidget(card)
            return lbl_val


        self.hud_voc = make_metric("V<sub>OC</sub> (V)")
        self.hud_jsc = make_metric("J<sub>SC</sub> (mA/cm\u00b2)")
        self.hud_pce = make_metric("PCE (%)")
        self.hud_ff  = make_metric("FILL FACTOR")

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
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header row
        header_row = QHBoxLayout()
        title_lbl = QLabel("EXTRACTED METRICS")
        title_lbl.setObjectName("PanelTitle")
        header_row.addWidget(title_lbl)
        header_row.addStretch(1)

        export_lbl = QLabel("MANUAL EXPORT:")
        export_lbl.setObjectName("DimLabel")
        header_row.addWidget(export_lbl)

        self.export_txt_btn = QPushButton("Export .TXT")
        self.export_txt_btn.clicked.connect(lambda: self.save_results(auto=False))
        header_row.addWidget(self.export_txt_btn)

        self.export_csv_btn = QPushButton("Export .CSV")
        self.export_csv_btn.clicked.connect(self.export_results_csv)
        header_row.addWidget(self.export_csv_btn)

        layout.addLayout(header_row)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        # Table wrap
        table_wrap = QFrame()
        table_wrap.setObjectName("TableWrap")
        table_wrap.setAttribute(Qt.WA_StyledBackground, True)
        table_wrap_layout = QVBoxLayout(table_wrap)
        table_wrap_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setObjectName("ResultsTable")
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setColumnCount(15)

        header = RichTextHeaderView(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(header)
        header.set_text_color(get_theme_colors(self.is_dark_mode)["accent"])

        self.table.setHorizontalHeaderLabels(
            ["Loop", "Pixel", "Area", "V<sub>oc</sub> (V)", "J<sub>sc</sub> (mA/cm\u00b2)", "FF",
             "PCE (%)", "V<sub>mpp</sub> (V)", "J<sub>mpp</sub> (mA/cm\u00b2)", "P<sub>max</sub> (mW/cm\u00b2)",
             "R<sub>s</sub> fit (\u03a9)", "R<sub>sh</sub> fit (\u03a9)",
             "R<sub>s</sub> deriv (\u03a9)", "R<sub>sh</sub> deriv (\u03a9)",
             "Status"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(430)
        table_wrap_layout.addWidget(self.table)

        layout.addWidget(table_wrap)

        self.add_panel_shadow(panel)
        return panel

    def build_log_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
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

    # Custom QTextFormat property ID used to tag each log run with its
    # semantic color role (e.g. "text_dim", "warning")
    _LOG_ROLE_PROPERTY = QTextFormat.UserProperty + 1

    def log_message(self, message):
        stamp = time.strftime("%H:%M:%S")
        colors = get_theme_colors(self.is_dark_mode)

        # Each log line renders as `[ts] PREFIX: rest`, w/ the prefix (and,
        # for WARNING/ERROR, the whole line) tinted by severity 
        prefix, sep, rest = message.partition(": ")
        prefix_key = prefix.strip().upper()

        severity_roles = {
            "OK": ("success", "text_main"),
            "WARNING": ("warning", "warning"),
            "ERROR": ("error", "error"),
        }

        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.End)
        if self.log.toPlainText():
            cursor.insertBlock()

        def write(text, role, bold=False):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colors[role]))
            fmt.setProperty(self._LOG_ROLE_PROPERTY, role)
            if bold:
                fmt.setFontWeight(QFont.Bold)
            cursor.setCharFormat(fmt)
            cursor.insertText(text)

        write(f"[{stamp}] ", "text_dim")

        if sep and prefix_key in severity_roles:
            prefix_role, text_role = severity_roles[prefix_key]
            write(f"{prefix}: ", prefix_role, bold=True)
            write(rest, text_role)
        else:
            write(message, "text_main")

        self.log.setTextCursor(cursor)
        self.log.moveCursor(QTextCursor.End) # Auto-scroll
        QApplication.processEvents()

    def _retheme_log(self):
        """Walks the log's existing text runs in place and updates each
        one's color from its tagged role, using the current theme."""
        colors = get_theme_colors(self.is_dark_mode)
        doc = self.log.document()

        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    role = frag.charFormat().property(self._LOG_ROLE_PROPERTY)
                    if role in colors:
                        run_cursor = QTextCursor(doc)
                        run_cursor.setPosition(frag.position())
                        run_cursor.setPosition(frag.position() + frag.length(), QTextCursor.KeepAnchor)
                        
                        # mergeCharFormat only touches the properties set here (foreground + role tag)
                        recolor_fmt = QTextCharFormat()
                        recolor_fmt.setForeground(QColor(colors[role]))
                        recolor_fmt.setProperty(self._LOG_ROLE_PROPERTY, role)
                        run_cursor.mergeCharFormat(recolor_fmt)
                it += 1
            block = block.next()


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
            and hasattr(self, "pixel_grid_widget")
            and obj is self.pixel_grid_widget
        ):
            self.recompute_pixel_grid_columns()
        return super().eventFilter(obj, event)

    def recompute_pixel_grid_columns(self):
        """Recomputes how many pixel cards fit per row based on the current panel width"""
        if not hasattr(self, "pixel_grid_widget"):
            return

        spacing = self.pixel_grid.spacing()
        card_w = self._pixel_card_min_width
        available = self.pixel_grid_widget.width()
        cols = max(1, (available + spacing) // (card_w + spacing))

        if cols != self._pixel_grid_cols:
            self._pixel_grid_cols = cols
            self._pixel_reflow_timer.start(120)

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

        colors = get_theme_colors(self.is_dark_mode)
        cols = getattr(self, "_pixel_grid_cols", 3)
        card_width = getattr(self, "_pixel_card_min_width", 160)
        for i, lab in enumerate(labels):
            card = QFrame()
            card.setObjectName("PixelCard")
            card.setAttribute(Qt.WA_StyledBackground, True)
            card.setStyleSheet(f"""
                QFrame#PixelCard {{
                    background-color: {colors['card_bg']};
                    border: 1px solid {colors['border']};
                    border-radius: 8px;
                }}
                QFrame#PixelCard:hover {{
                    border-color: {colors['accent']};
                }}
            """)
            card.setFixedWidth(card_width)
            card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(8)

            cb = QCheckBox()
            cb.setStyleSheet("border: none; background: transparent;")
            cb.setChecked(True)
            cb.setProperty("pixel_label", lab)

            letter_lbl = QLabel(lab)
            letter_lbl.setStyleSheet("font-weight: bold; font-size: 20px; border: none; background: transparent;")

            area = NoWheelDoubleSpinBox()
            area.setRange(0.0001, 100)
            area.setDecimals(4)
            area.setValue(area_default)
            area.setFixedWidth(82)
            area.setStyleSheet("border: none; background: transparent; padding: 0px; font-size: 13px;")

            card_layout.addWidget(cb)
            card_layout.addWidget(letter_lbl)
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

    def _animate_tab_switch(self, index):
        """Fades the newly-selected tab's content in while sliding it up a
        few pixels"""
        widget = self.tabs.widget(index)
        if widget is None:
            return

        opacity_effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(opacity_effect)

        fade = QPropertyAnimation(opacity_effect, b"opacity", self)
        fade.setDuration(250)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)

        end_rect = widget.geometry()
        start_rect = end_rect.translated(0, 8)
        slide = QPropertyAnimation(widget, b"geometry", self)
        slide.setDuration(250)
        slide.setStartValue(start_rect)
        slide.setEndValue(end_rect)
        slide.setEasingCurve(QEasingCurve.OutCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(fade)
        group.addAnimation(slide)
        
        # Drop the opacity effect once the animation finishes
        group.finished.connect(lambda: widget.setGraphicsEffect(None))
        group.start(QAbstractAnimation.DeleteWhenStopped)

        # Keep a reference so Python's GC can't collect the group mid-flight
        # before Qt's DeleteWhenStopped policy cleans it up itself.
        self._tab_switch_anim = group

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_style()

        # Force SafeTabBar to fully recompute its size.
        tab_bar = self.tabs.tabBar()
        tab_bar.style().unpolish(tab_bar)
        tab_bar.style().polish(tab_bar)
        tab_bar.updateGeometry()
        
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

        # Refresh the rich-text header's accent color
        if hasattr(self, "table"):
            header = self.table.horizontalHeader()
            if isinstance(header, RichTextHeaderView):
                header.set_text_color(colors["accent"])

        # Rebuild pixel cards so their colors (set via an inline stylesheet,
        # not the global QSS cascade — see build_pixels()) don't stay stuck
        # in the previous theme
        if hasattr(self, "pixel_grid"):
            self.build_pixels()

        # Refresh LED glow colors for the new theme
        for led in (self.keithley_led, self.relay_led):
            self._refresh_led_glow(led)

        # Recolor the log's existing text runs in place
        if hasattr(self, "log"):
            self._retheme_log()
    
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
                pixel = checkbox.property("pixel_label")
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
        self.hud_active_pixel.setText(f"Latest Pixel: {record['pixel']}")
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
        if not self.results:
            if not auto:
                self.log_message("WARNING: No results to save")
            return

        # Sync the exporter's config from the live widgets, then delegate
        # all path-building and file-writing to core/exporter.py.
        self.exporter.output_dir = self.output_dir
        self.exporter.sample_name = self.file.text().strip() or "solar_iv_data"

        if not auto:
            # Manual export (button click)
            chosen_dir = QFileDialog.getExistingDirectory(
                self, "Choose Folder to Save TXT Results", self.output_dir,
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )
            if not chosen_dir:
                return  # user cancelled
            self.exporter.output_dir = chosen_dir

        self.exporter.save_results(self.results, auto=auto)

    def export_plot_png(self):
        try:
            import pyqtgraph.exporters

            self.exporter.output_dir = self.output_dir
            self.exporter.sample_name = self.file.text().strip() or "solar_iv_data"
            folder = self.exporter.build_daily_output_dir()
            timestamp = time.strftime("%H%M%S")
            basename = self.exporter._basename()
            suggested_path = os.path.join(folder, f"{basename}_ivcurve_{timestamp}.png")

            path, _ = QFileDialog.getSaveFileName(
                self, "Export IV Curve Image", suggested_path, "PNG Image (*.png)"
            )
            if not path:
                return  # user cancelled

            image_exporter = pyqtgraph.exporters.ImageExporter(self.plot_manager.plot.getPlotItem())
            image_exporter.parameters()["width"] = 1600
            image_exporter.export(path)
            self.log_message(f"OK: Exported plot image to {path}")
        except Exception as e:
            self.log_message(f"ERROR: could not export plot image: {e}")

    def export_results_csv(self):
        """Writes the on-screen results table to a CSV file, alongside the
        existing per-pixel TXT export path. Reads from the table itself
        (rather than self.results) so exactly what's displayed is exported,
        column headers included."""
        if self.table.rowCount() == 0:
            self.log_message("WARNING: No results to export")
            return

        try:
            import csv

            self.exporter.output_dir = self.output_dir
            self.exporter.sample_name = self.file.text().strip() or "solar_iv_data"
            folder = self.exporter.build_daily_output_dir()
            timestamp = time.strftime("%H%M%S")
            basename = self.exporter._basename()
            suggested_path = os.path.join(folder, f"{basename}_results_{timestamp}.csv")

            path, _ = QFileDialog.getSaveFileName(
                self, "Export Results CSV", suggested_path, "CSV File (*.csv)"
            )
            if not path:
                return  # user cancelled

            # Column headers are rich-text (e.g. "P<sub>max</sub> (mW/cm\u00b2)")
            # for on-screen display; strip the markup back to plain text for
            # the CSV so it stays readable in a spreadsheet.
            headers = []
            for col in range(self.table.columnCount()):
                header_item = self.table.horizontalHeaderItem(col)
                raw = header_item.text() if header_item else ""
                plain = raw.replace("<sub>", "").replace("</sub>", "")
                headers.append(plain)

            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in range(self.table.rowCount()):
                    row = [
                        self.table.item(r, c).text() if self.table.item(r, c) else ""
                        for c in range(self.table.columnCount())
                    ]
                    writer.writerow(row)
            self.log_message(f"OK: Exported {self.table.rowCount()} row(s) to {path}")
        except Exception as e:
            self.log_message(f"ERROR: could not export CSV: {e}")

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

