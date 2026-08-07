"""
JV "SWEEP" tab: the live IV curve plot plus the live-metrics HUD sitting
beside it. Owns a PlotManager instance. Exposes plain setter methods for
the controller to push live data in as the sweep runs.
"""
from atom.api import Atom, Bool, Callable, Event, List, Typed
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton

from gui.plot_manager import PlotManager
from gui.effects import make_panel_shadow, update_shadow_color
from gui.style import get_theme_colors


class JVPlotPanel(Atom):
    __slots__ = ('__weakref__',)

    is_dark_mode = Bool(False)

    abort_requested = Event()
    export_png_requested = Event()

    _widget = Typed(QWidget)
    plot_manager = Typed(PlotManager)
    _hud_active_pixel = Typed(QLabel)
    _hud_voc = Typed(QLabel)
    _hud_jsc = Typed(QLabel)
    _hud_pce = Typed(QLabel)
    _hud_ff = Typed(QLabel)
    _hud_abort = Typed(QPushButton)
    _shadow_widgets = List()
    _log = Callable(lambda message: None)  # replaced via set_logger()

    def get_widget(self):
        return self._widget

    def create_widget(self, parent):
        container = QWidget(parent)
        layout = QHBoxLayout(container)
        layout.setSpacing(15)
        layout.addWidget(self._build_plot_panel(), 3)
        layout.addWidget(self._build_live_hud(), 1)
        self._widget = container
        return container

    def _build_plot_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.plot_manager = PlotManager(
            range_dialog_callback=lambda: self.plot_manager.open_range_dialog(
                self.get_widget(), self._log
            )
        )
        layout.addWidget(self.plot_manager.widget, 1)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(8)

        reset_view_btn = QPushButton("Reset View")
        reset_view_btn.clicked.connect(self.plot_manager.apply_default_range)
        tools_row.addWidget(reset_view_btn)

        set_range_btn = QPushButton("Set Range...")
        set_range_btn.clicked.connect(
            lambda: self.plot_manager.open_range_dialog(self.get_widget(), self._log)
        )
        tools_row.addWidget(set_range_btn)

        export_png_btn = QPushButton("Export PNG")
        export_png_btn.clicked.connect(self._on_export_png_clicked)
        tools_row.addWidget(export_png_btn)

        tools_row.addStretch(1)
        layout.addLayout(tools_row)

        colors = get_theme_colors(self.is_dark_mode)
        plot = self.plot_manager.widget
        plot.setBackground(colors["bg_panel"])
        plot.getAxis("bottom").setPen(pg.mkPen(colors["border"]))
        plot.getAxis("left").setPen(pg.mkPen(colors["border"]))
        plot.getAxis("bottom").setTextPen(pg.mkPen(colors["text_dim"]))
        plot.getAxis("left").setTextPen(pg.mkPen(colors["text_dim"]))

        self._add_shadow(panel)
        return panel

    def _build_live_hud(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self._hud_active_pixel = QLabel("Latest Pixel: --")
        self._hud_active_pixel.setObjectName("HudActivePixel")
        layout.addWidget(self._hud_active_pixel)

        divider2 = QFrame()
        divider2.setObjectName("Divider")
        divider2.setFrameShape(QFrame.HLine)
        layout.addWidget(divider2)

        def make_metric(label_html):
            card = QFrame()
            card.setObjectName("MetricCard")
            card.setAttribute(Qt.WA_StyledBackground, True)
            card.setMinimumHeight(108)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            card_layout.setSpacing(6)
            card_layout.setAlignment(Qt.AlignHCenter)

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

        self._hud_voc = make_metric("V<sub>OC</sub> (V)")
        self._hud_jsc = make_metric("J<sub>SC</sub> (mA/cm\u00b2)")
        self._hud_pce = make_metric("PCE (%)")
        self._hud_ff = make_metric("FILL FACTOR")

        layout.addStretch()

        self._hud_abort = QPushButton("ABORT SWEEP")
        self._hud_abort.setObjectName("DangerButton")
        self._hud_abort.setMinimumHeight(42)
        self._hud_abort.clicked.connect(self._on_abort_clicked)
        self._hud_abort.setEnabled(False)
        layout.addWidget(self._hud_abort)

        self._add_shadow(panel)
        return panel

    def _add_shadow(self, widget):
        effect = make_panel_shadow(widget, self.is_dark_mode)
        self._shadow_widgets = self._shadow_widgets + [effect]

    def _on_abort_clicked(self):
        self.abort_requested = True

    def _on_export_png_clicked(self):
        self.export_png_requested = True

    # --- Public API for the controller ---

    def set_logger(self, log_fn):
        self._log = log_fn

    def reset_for_new_run(self):
        self.plot_manager.clear_curves()
        self.plot_manager.clear_legends()
        self.plot_manager.apply_default_range()
        self._hud_active_pixel.setText("Latest Pixel: --")
        for lbl in (self._hud_voc, self._hud_jsc, self._hud_pce, self._hud_ff):
            lbl.setText("--")

    def prepare_legends(self, selected_pixels, loop_count):
        self.plot_manager.reset_legends(selected_pixels, loop_count)

    def plot_curve(self, V, J, channel, loop_number):
        self.plot_manager.plot_curve(V, J, channel, loop_number)

    def set_active_pixel(self, pixel):
        self._hud_active_pixel.setText(f"Latest Pixel: {pixel}")

    def set_hud_metrics(self, voc_text, jsc_text, pce_text, ff_text):
        self._hud_voc.setText(voc_text)
        self._hud_jsc.setText(jsc_text)
        self._hud_pce.setText(pce_text)
        self._hud_ff.setText(ff_text)

    def set_running(self, running):
        self._hud_abort.setEnabled(running)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        for effect in self._shadow_widgets:
            update_shadow_color(effect, is_dark_mode)
        plot = self.plot_manager.widget
        plot.setBackground(colors["bg_panel"])
        plot.getAxis("bottom").setPen(pg.mkPen(colors["border"]))
        plot.getAxis("left").setPen(pg.mkPen(colors["border"]))
        plot.getAxis("bottom").setTextPen(pg.mkPen(colors["text_dim"]))
        plot.getAxis("left").setTextPen(pg.mkPen(colors["text_dim"]))
