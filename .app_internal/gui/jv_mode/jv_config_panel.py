"""
JV "CONFIG" tab: sweep-parameter form on the left, pixel matrix on the
right. Owns and validates its own inputs.
"""
from atom.api import Bool, Event, List, Typed, Value
from enaml.core.declarative import d_
from enaml.widgets.raw_widget import RawWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel,
    QCheckBox, QPushButton, QSizePolicy, QLayout,
)

from controllers.jv_worker import (
    PIXEL_TO_RELAY_CHANNEL,
    active_pixel_labels,
    default_pixel_area,
    pixel_uses_relay,
)
from instruments.keithley2460 import KEITHLEY_DEFAULT_COMPLIANCE_A
from gui.custom_widgets import NoWheelSpinBox, NoWheelDoubleSpinBox, NoWheelComboBox
from gui.effects import make_panel_shadow, update_shadow_color
from gui.style import get_theme_colors


class JVConfigPanel(RawWidget):
    __slots__ = ('__weakref__',)

    is_dark_mode = d_(Bool(False))

    run_requested = d_(Event(), writable=False)
    layout_changed = d_(Event(), writable=False)

    # Sweep-parameter inputs
    _v0 = Typed(NoWheelDoubleSpinBox)
    _v1 = Typed(NoWheelDoubleSpinBox)
    _points = Typed(NoWheelSpinBox)
    _dir = Typed(NoWheelComboBox)
    _loops = Typed(NoWheelSpinBox)
    _point_delay = Typed(NoWheelDoubleSpinBox)
    _compliance_ma = Typed(NoWheelDoubleSpinBox)
    _pin = Typed(NoWheelDoubleSpinBox)
    _start_btn = Typed(QPushButton)

    # Pixel matrix
    _pixel_mode = Typed(NoWheelComboBox)
    _pixel_grid = Typed(QGridLayout)
    _pixel_grid_widget = Typed(QWidget)
    _checks = List()   # [QCheckBox, ...], rebuilt wholesale by _build_pixels
    _areas = List()    # [NoWheelDoubleSpinBox, ...], parallel to _checks

    _top_layout = Typed(QHBoxLayout)
    _sweep_panel = Typed(QFrame)
    _shadow_widgets = List()
    _pixel_reflow_timer = Typed(QTimer)
    _pixel_card_min_width = Value(230)
    _pixel_grid_cols = Value(3)

    def create_widget(self, parent):
        container = QWidget(parent)

        self._pixel_reflow_timer = QTimer(container)
        self._pixel_reflow_timer.setSingleShot(True)
        self._pixel_reflow_timer.timeout.connect(self._build_pixels)

        self._top_layout = layout = QHBoxLayout(container)
        layout.setSpacing(15)
        layout.setSizeConstraint(QLayout.SetNoConstraint)
        self._sweep_panel = self._build_sweep_panel()
        layout.addWidget(self._sweep_panel, 1)
        layout.addWidget(self._build_pixel_panel(), 2)

        return container

    # --- Sweep panel ---

    def _build_sweep_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(0)

        title_lbl = QLabel("SWEEP SETUP")
        title_lbl.setObjectName("PanelTitle")
        title_lbl.setStyleSheet("padding-bottom: 8px;")
        layout.addWidget(title_lbl)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        self._v0 = NoWheelDoubleSpinBox()
        self._v0.setRange(-5, 5)
        self._v0.setDecimals(2)
        self._v0.setValue(-0.2)

        self._v1 = NoWheelDoubleSpinBox()
        self._v1.setRange(-5, 5)
        self._v1.setDecimals(2)
        self._v1.setValue(1.3)

        self._points = NoWheelSpinBox()
        self._points.setRange(2, 2000)
        self._points.setValue(100)

        self._dir = NoWheelComboBox()
        self._dir.addItems(["Forward", "Reverse"])
        self._dir.setCurrentText("Reverse")

        self._loops = NoWheelSpinBox()
        self._loops.setRange(1, 20)
        self._loops.setValue(1)

        self._point_delay = NoWheelDoubleSpinBox()
        self._point_delay.setRange(0.001, 10)
        self._point_delay.setDecimals(2)
        self._point_delay.setValue(0.01)

        self._compliance_ma = NoWheelDoubleSpinBox()
        self._compliance_ma.setRange(0.001, 1000)
        self._compliance_ma.setDecimals(0)
        self._compliance_ma.setValue(KEITHLEY_DEFAULT_COMPLIANCE_A * 1000)

        self._pin = NoWheelDoubleSpinBox()
        self._pin.setRange(0.001, 5000)
        self._pin.setDecimals(0)
        self._pin.setValue(100.0)

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

        layout.addWidget(make_row("Start Voltage (V)", self._v0))
        layout.addWidget(make_row("Stop Voltage (V)", self._v1))
        layout.addWidget(make_row("Step Count", self._points))
        layout.addWidget(make_row("Direction", self._dir))
        layout.addWidget(make_row("Loops", self._loops))
        layout.addWidget(make_row("Point Delay (s)", self._point_delay))
        layout.addWidget(make_row("Compliance (mA)", self._compliance_ma))
        layout.addWidget(make_row("Irradiance (mW/cm\u00b2)", self._pin))

        layout.addStretch(1)

        self._start_btn = QPushButton("INITIALIZE RUN")
        self._start_btn.setObjectName("PrimaryButton")
        self._start_btn.setMinimumHeight(44)
        self._start_btn.clicked.connect(self._on_run_clicked)
        layout.addWidget(self._start_btn)

        self._add_shadow(panel)
        return panel

    def _on_run_clicked(self):
        self.run_requested = True

    # --- Pixel panel ---

    def _build_pixel_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        title_lbl = QLabel("PIXEL MATRIX \u2014 Area (cm\u00b2)")
        title_lbl.setObjectName("PanelTitle")
        title_lbl.setWordWrap(True)
        title_lbl.setMinimumWidth(0)
        header_row.addWidget(title_lbl, 1)

        self._pixel_mode = NoWheelComboBox()
        self._pixel_mode.setMinimumWidth(110)
        self._pixel_mode.addItems(["6 Pixels", "12 Pixels", "Custom"])
        self._pixel_mode.currentIndexChanged.connect(self._build_pixels)
        header_row.addWidget(self._pixel_mode)
        layout.addLayout(header_row)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        self._pixel_grid = QGridLayout()
        self._pixel_grid.setSpacing(10)
        self._pixel_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._pixel_grid_widget = QWidget()
        self._pixel_grid_widget.setStyleSheet("background: transparent; border: none;")
        self._pixel_grid_widget.setLayout(self._pixel_grid)
        self._pixel_grid_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        layout.addWidget(self._pixel_grid_widget)
        layout.addStretch(1)

        self._build_pixels()

        self._add_shadow(panel)
        return panel

    def set_available_content_width(self, available_width):
        """Recompute the pixel-grid column count from a supplied
        width (e.g. the scroll area's viewport width) rather than this
        panel's own current width."""

        margins = self._top_layout.contentsMargins()
        sweep_min_width = self._sweep_panel.minimumSizeHint().width()
        content_width = (
            available_width
            - margins.left() - margins.right()
            - self._top_layout.spacing()
            - sweep_min_width
            - 18 * 2  # pixel panel's own content margins
        )
        content_width = max(0, content_width)

        spacing = self._pixel_grid.spacing()
        card_w = self._pixel_card_min_width
        cols = max(1, int((content_width + spacing) // (card_w + spacing)))

        if cols != self._pixel_grid_cols:
            self._pixel_grid_cols = cols
            self._pixel_reflow_timer.start(60)

    def _build_pixels(self):
        for i in reversed(range(self._pixel_grid.count())):
            item = self._pixel_grid.itemAt(i)
            if item.widget():
                widget = item.widget()
                self._pixel_grid.removeWidget(widget)
                widget.deleteLater()                  

        self._checks = []
        self._areas = []

        pixel_mode = self._pixel_mode.currentText()
        labels = active_pixel_labels(pixel_mode)
        area_default = default_pixel_area(pixel_mode)

        colors = get_theme_colors(self.is_dark_mode)
        cols = self._pixel_grid_cols
        card_width = self._pixel_card_min_width
        checks = []
        areas = []
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
            label_font_size = 20 if len(lab) == 1 else 14
            letter_lbl.setStyleSheet(
                f"font-weight: bold; font-size: {label_font_size}px; border: none; background: transparent;"
            )

            area = NoWheelDoubleSpinBox()
            area.setRange(0.0001, 100)
            area.setDecimals(4)
            area.setValue(area_default)
            area.setSuffix(" cm\u00b2")
            area.setFixedWidth(100)
            area.setStyleSheet("border: none; background: transparent; padding: 0px; font-size: 13px;")

            card_layout.addWidget(cb)
            card_layout.addWidget(letter_lbl)
            card_layout.addStretch(1)
            card_layout.addWidget(area)

            checks.append(cb)
            areas.append(area)

            row = i // cols
            col = i % cols
            self._pixel_grid.addWidget(card, row, col)

        self._checks = checks
        self._areas = areas

        self._pixel_grid.invalidate()
        widget = self.get_widget()
        if widget is not None:
            widget.updateGeometry()
        self.layout_changed = True

    def _add_shadow(self, widget):
        effect = make_panel_shadow(widget, self.is_dark_mode)
        self._shadow_widgets = self._shadow_widgets + [effect]

    # --- Public API for the controller ---

    def refresh_layout(self, available_width=None):
        if available_width is not None:
            self.set_available_content_width(available_width)
        self._build_pixels()
        widget = self.get_widget()
        if widget is not None:
            widget.updateGeometry()

    def validate(self):
        """Panel-local validation only (voltage range, pixel selection).
        Instrument-connection validation is the controller's job."""
        if self._v0.value() == self._v1.value():
            return "ERROR: Start and Stop voltage cannot be the same."
        if not any(cb.isChecked() for cb in self._checks):
            return "ERROR: Please select at least one pixel."
        return None

    def get_sweep_params(self):
        return {
            "v0": self._v0.value(),
            "v1": self._v1.value(),
            "reverse": self._dir.currentText() == "Reverse",
            "pin": self._pin.value(),
            "compliance_a": self._compliance_ma.value() / 1000,
            "point_delay_s": self._point_delay.value(),
            "loops": self._loops.value(),
            "points": self._points.value(),
        }

    def get_selected_pixels(self):
        use_relay = pixel_uses_relay(self._pixel_mode.currentText())
        selected = []
        for i, checkbox in enumerate(self._checks):
            if checkbox.isChecked():
                pixel = checkbox.property("pixel_label")
                channel = PIXEL_TO_RELAY_CHANNEL[pixel] if use_relay else None
                selected.append((pixel, channel, self._areas[i].value()))
        return selected

    def set_running(self, running):
        self._start_btn.setEnabled(not running)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        for effect in self._shadow_widgets:
            update_shadow_color(effect, is_dark_mode)
        self._build_pixels()
