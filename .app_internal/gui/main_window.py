"""
Builds the header, the mode tabs, the log panel, and the footer progress strip. then hands them off to the
controllers to process respective button presses.
"""
import os
import sys

import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QProgressBar, QTabWidget, QScrollArea

from core.instrument_manager import InstrumentManager
from core.exporter import ResultsExporter

from controllers.main_controller import MainController
from controllers.jv_controller import JVController

from gui.custom_widgets import SafeTabBar
from gui.style import get_theme, get_theme_colors
from gui.effects import make_panel_shadow, update_shadow_color, animate_tab_switch

from gui.common_panels.header_panel import HeaderPanel
from gui.common_panels.log_panel import LogPanel

from gui.jv_mode.jv_config_panel import JVConfigPanel
from gui.jv_mode.jv_plot_panel import JVPlotPanel
from gui.jv_mode.jv_results_panel import JVResultsPanel

CONFIG_TAB_INDEX = 0
SWEEP_TAB_INDEX = 1
RESULTS_TAB_INDEX = 2
LOGS_TAB_INDEX = 3


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.is_dark_mode = False
        self._shadow_widgets = []
        self._theme_aware_panels = []  # anything with an apply_theme(colors, is_dark_mode) method

        self.setWindowTitle("Multiplex Solar Simulator - IV Characterization")
        self.resize(1440, 900)
        self.setMinimumSize(1024, 680)
        self.setObjectName("Root")

        self.output_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.instrument_manager = InstrumentManager()

        self.apply_style()
        self._build_ui()
        self._wire_controllers()

        QTimer.singleShot(0, self.jv_config_panel.refresh_layout)

    def apply_style(self):
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet(get_theme(self.is_dark_mode))

    # --- Layout assembly ---

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(10)

        self.header_panel = HeaderPanel(self.is_dark_mode)
        self._register_theme_aware(self.header_panel)
        self.header_panel.theme_toggled.connect(self.toggle_theme)
        main.addWidget(self.header_panel)

        self.tabs = QTabWidget()
        self.tabs.setTabBar(SafeTabBar(self.tabs))
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        self.tabs.tabBar().setExpanding(False)

        # Small screens (1080p and below) fix: Scrolls instead of clipping buttons off the bottom of the window.
        # per instance size constraints is overceded.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.tabs)
        main.addWidget(scroll, 1)

        # TAB 1: CONFIG
        self.jv_config_panel = JVConfigPanel(self.is_dark_mode)
        self._register_theme_aware(self.jv_config_panel)
        self.tabs.addTab(self.jv_config_panel, "1. CONFIG")

        # TAB 2: SWEEP
        self.jv_plot_panel = JVPlotPanel(self.is_dark_mode)
        self._register_theme_aware(self.jv_plot_panel)
        self.tabs.addTab(self.jv_plot_panel, "2. SWEEP")

        # TAB 3: RESULTS
        self.jv_results_panel = JVResultsPanel(self.is_dark_mode)
        self._register_theme_aware(self.jv_results_panel)
        self.tabs.addTab(self.jv_results_panel, "3. RESULTS")

        # TAB 4: LOGS
        self.log_panel = LogPanel(self.output_dir, self.is_dark_mode)
        self._register_theme_aware(self.log_panel)
        self.tabs.addTab(self.log_panel, "4. LOGS")

        self.tabs.currentChanged.connect(self._on_tab_changed)

        main.addWidget(self._build_footer())

    def _build_footer(self):
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
        footer_layout.addWidget(self.progress_bar, 1)

        self.progress_pct = QLabel("0%")
        self.progress_pct.setObjectName("MainLabel")
        footer_layout.addWidget(self.progress_pct)

        divider = QFrame()
        divider.setObjectName("VDivider")
        divider.setFrameShape(QFrame.VLine)
        footer_layout.addWidget(divider)

        self.progress_txt = QLabel("Ready")
        self.progress_txt.setObjectName("DimLabel")
        footer_layout.addWidget(self.progress_txt)

        self.footer.setVisible(False)
        self._footer_shadow = make_panel_shadow(self.footer, self.is_dark_mode)
        return self.footer

    def _register_theme_aware(self, panel):
        self._theme_aware_panels.append(panel)

    # --- Controller wiring ---

    def _wire_controllers(self):
        self.exporter = ResultsExporter(self.output_dir, "Sample", self.log_panel.log_message)

        self.main_controller = MainController(
            instrument_manager=self.instrument_manager,
            header_panel=self.header_panel,
            log_panel=self.log_panel,
            get_colors=lambda: get_theme_colors(self.is_dark_mode),
            parent_widget=self,
        )

        self.jv_controller = JVController(
            instrument_manager=self.instrument_manager,
            exporter=self.exporter,
            config_panel=self.jv_config_panel,
            plot_panel=self.jv_plot_panel,
            results_panel=self.jv_results_panel,
            log_fn=self.log_panel.log_message,
            get_sample_name=self.header_panel.sample_name,
            tabs=self.tabs,
            sweep_tab_index=SWEEP_TAB_INDEX,
            parent_widget=self,
        )
        self.main_controller.register_mode_controller(self.jv_controller)

        # Cross-panel running state (start/abort/connect/browse all need
        # to agree on whether a sweep is in flight).
        self.jv_controller.running_changed.connect(self._on_running_changed)
        self.jv_controller.progress_changed.connect(self._on_progress_update)

    # --- Cross-cutting state broadcasts ---

    def _on_running_changed(self, running):
        self.header_panel.set_running(running)
        self.footer.setVisible(running)
        if running:
            self.progress_bar.setValue(0)
            self.progress_pct.setText("0%")
            self.progress_txt.setText("Initializing hardware...")

    def _on_progress_update(self, percent, text):
        self.progress_bar.setValue(percent)
        self.progress_pct.setText(f"{percent}%")
        self.progress_txt.setText(text)

    def _on_tab_changed(self, index):
        animate_tab_switch(self.tabs, index, anim_owner=self)

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_style()

        tab_bar = self.tabs.tabBar()
        tab_bar.style().unpolish(tab_bar)
        tab_bar.style().polish(tab_bar)
        tab_bar.updateGeometry()

        colors = get_theme_colors(self.is_dark_mode)
        update_shadow_color(self._footer_shadow, self.is_dark_mode)

        for panel in self._theme_aware_panels:
            panel.apply_theme(colors, self.is_dark_mode)
