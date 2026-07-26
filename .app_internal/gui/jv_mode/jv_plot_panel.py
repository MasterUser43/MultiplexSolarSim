"""
JV "SWEEP" tab: the live IV curve plot plus the live-metrics HUD sitting
beside it. Owns a PlotManager instance. Exposes plain setter methods for
the controller to push live data in as the sweep runs.
"""
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton

from gui.plot_manager import PlotManager
from gui.effects import make_panel_shadow, update_shadow_color
from gui.style import get_theme_colors


class JVPlotPanel(QWidget):
    abort_requested = pyqtSignal()
    export_png_requested = pyqtSignal()

    def __init__(self, is_dark_mode=False, parent=None):
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self._shadow_widgets = []

        layout = QHBoxLayout(self)
        layout.setSpacing(15)
        layout.addWidget(self._build_plot_panel(), 3)
        layout.addWidget(self._build_live_hud(), 1)

    def _build_plot_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.plot_manager = PlotManager(
            range_dialog_callback=lambda: self.plot_manager.open_range_dialog(self, self._log)
        )
        self.plot = self.plot_manager.widget
        layout.addWidget(self.plot, 1)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(8)

        reset_view_btn = QPushButton("Reset View")
        reset_view_btn.clicked.connect(self.plot_manager.apply_default_range)
        tools_row.addWidget(reset_view_btn)

        set_range_btn = QPushButton("Set Range...")
        set_range_btn.clicked.connect(
            lambda: self.plot_manager.open_range_dialog(self, self._log)
        )
        tools_row.addWidget(set_range_btn)

        self.export_png_btn = QPushButton("Export PNG")
        self.export_png_btn.clicked.connect(self.export_png_requested.emit)
        tools_row.addWidget(self.export_png_btn)

        tools_row.addStretch(1)
        layout.addLayout(tools_row)

        colors = get_theme_colors(self.is_dark_mode)
        self.plot.setBackground(colors["bg_panel"])
        self.plot.getAxis("bottom").setPen(pg.mkPen(colors["border"]))
        self.plot.getAxis("left").setPen(pg.mkPen(colors["border"]))
        self.plot.getAxis("bottom").setTextPen(pg.mkPen(colors["text_dim"]))
        self.plot.getAxis("left").setTextPen(pg.mkPen(colors["text_dim"]))

        self._add_shadow(panel)
        return panel

    def _build_live_hud(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title_lbl = QLabel("LIVE STATUS")
        title_lbl.setObjectName("PanelTitleLarge")
        layout.addWidget(title_lbl)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        self.hud_active_pixel = QLabel("Latest Pixel: --")
        self.hud_active_pixel.setObjectName("HudActivePixel")
        layout.addWidget(self.hud_active_pixel)

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

        self.hud_voc = make_metric("V<sub>OC</sub> (V)")
        self.hud_jsc = make_metric("J<sub>SC</sub> (mA/cm\u00b2)")
        self.hud_pce = make_metric("PCE (%)")
        self.hud_ff = make_metric("FILL FACTOR")

        layout.addStretch()

        self.hud_abort = QPushButton("ABORT SWEEP")
        self.hud_abort.setObjectName("DangerButton")
        self.hud_abort.setMinimumHeight(42)
        self.hud_abort.clicked.connect(self.abort_requested.emit)
        self.hud_abort.setEnabled(False)
        layout.addWidget(self.hud_abort)

        self._add_shadow(panel)
        return panel

    def _add_shadow(self, widget):
        effect = make_panel_shadow(widget, self.is_dark_mode)
        self._shadow_widgets.append(effect)

    def _log(self, message):
        """Fallback no-op logger for PlotManager's range-dialog error path
        until the controller wires a real one in via set_logger()."""
        pass

    # --- Public API for the controller ---

    def set_logger(self, log_fn):
        self._log = log_fn

    def reset_for_new_run(self):
        self.plot_manager.clear_curves()
        self.plot_manager.clear_legends()
        self.plot_manager.apply_default_range()
        self.hud_active_pixel.setText("Latest Pixel: --")
        for lbl in (self.hud_voc, self.hud_jsc, self.hud_pce, self.hud_ff):
            lbl.setText("--")

    def prepare_legends(self, selected_pixels, loop_count):
        self.plot_manager.reset_legends(selected_pixels, loop_count)

    def plot_curve(self, V, J, channel, loop_number):
        self.plot_manager.plot_curve(V, J, channel, loop_number)

    def set_active_pixel(self, pixel):
        self.hud_active_pixel.setText(f"Latest Pixel: {pixel}")

    def set_hud_metrics(self, voc_text, jsc_text, pce_text, ff_text):
        self.hud_voc.setText(voc_text)
        self.hud_jsc.setText(jsc_text)
        self.hud_pce.setText(pce_text)
        self.hud_ff.setText(ff_text)

    def set_running(self, running):
        self.hud_abort.setEnabled(running)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        for effect in self._shadow_widgets:
            update_shadow_color(effect, is_dark_mode)
        self.plot_manager.plot.setBackground(colors["bg_panel"])
        self.plot_manager.plot.getAxis("bottom").setPen(pg.mkPen(colors["border"]))
        self.plot_manager.plot.getAxis("left").setPen(pg.mkPen(colors["border"]))
        self.plot_manager.plot.getAxis("bottom").setTextPen(pg.mkPen(colors["text_dim"]))
        self.plot_manager.plot.getAxis("left").setTextPen(pg.mkPen(colors["text_dim"]))
