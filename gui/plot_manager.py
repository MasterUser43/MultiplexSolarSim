"""
Encapsulates the pyqtgraph side of the IV plot: axis setup, per-pixel and
per-loop pen styling, the dual pixel/loop legend system, and the
right-click range dialog.

This module only interacts with PyQt/pyqtgraph, only focusing on rendering
curves.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
import pyqtgraph as pg

from gui.custom_widgets import NoWheelViewBox, NoWheelDoubleSpinBox

PIXEL_COLORS = [
    "#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#004c6d", "#a05195",
]

LOOP_DASH_PATTERNS = [
    None,                       # Loop 1: solid
    [7, 4],                     # Loop 2: dashed
    [1, 3],                     # Loop 3: dotted
    [7, 3, 1.5, 3, 7, 5],       # Loop 4: dash-dot-dash
    [7, 3, 1.5, 3, 1.5, 5],     # Loop 5: dash-dot-dot
    [12, 4],
    [4, 3],
    [10, 3, 3, 3],
]


class PlotManager:
    """
    The GUI creates one of these, adds `plot_manager.widget` to its layout,
    and calls through this object for anything plot-related.
    """

    def __init__(self, range_dialog_callback=None):
        self.plot = pg.PlotWidget(viewBox=NoWheelViewBox(range_dialog_callback))
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

        self.pixel_legend = None
        self.loop_legend = None
        self.apply_default_range()

    @property
    def widget(self):
        return self.plot

    def apply_default_range(self):
        self.plot.enableAutoRange(x=False, y=False)
        self.plot.setXRange(0, 1.3, padding=0)
        self.plot.setYRange(0, 26, padding=0)

    def clear_curves(self):
        self.plot.clear()

    def pixel_color(self, channel):
        return PIXEL_COLORS[channel % len(PIXEL_COLORS)]

    def loop_pen(self, loop_number, color="#243b53", width=2):
        pattern = LOOP_DASH_PATTERNS[(int(loop_number) - 1) % len(LOOP_DASH_PATTERNS)]
        pen = pg.mkPen(color=color, width=width)

        if pattern is None:
            pen.setStyle(Qt.SolidLine)
        else:
            pen.setStyle(Qt.CustomDashLine)
            pen.setDashPattern(pattern)

        return pen

    def curve_pen(self, channel, loop_number):
        return self.loop_pen(loop_number, color=self.pixel_color(channel), width=2)

    def plot_curve(self, V, J, channel, loop_number):
        self.plot.plot(V, J, pen=self.curve_pen(channel, loop_number))

    def _remove_legend(self, legend):
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

    def clear_legends(self):
        plot_item = self.plot.getPlotItem()
        existing = getattr(plot_item, "legend", None)
        self._remove_legend(existing)
        plot_item.legend = None

        if self.loop_legend is not None and self.loop_legend is not existing:
            self._remove_legend(self.loop_legend)

        self.pixel_legend = None
        self.loop_legend = None

    def reset_legends(self, selected_pixels, loop_count):
        self.clear_legends()

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

    def open_range_dialog(self, parent, log_callback):
        view_range = self.plot.getViewBox().viewRange()
        (x_min_current, x_max_current), (y_min_current, y_max_current) = view_range

        dialog = QDialog(parent)
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
                log_callback("ERROR: plot range maximum must be greater than minimum")
                return
            self.plot.setXRange(x_min.value(), x_max.value(), padding=0)
            self.plot.setYRange(y_min.value(), y_max.value(), padding=0)
