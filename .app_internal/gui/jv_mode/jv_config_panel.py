"""
JV "CONFIG" tab: sweep-parameter form on the left, substrate diagram +
dataset card on the right. Owns and validates its own inputs.
"""
import functools

from atom.api import Bool, Event, List, Typed, Value
from enaml.core.declarative import d_
from enaml.widgets.raw_widget import RawWidget
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel,
    QCheckBox, QPushButton, QLineEdit, QLayout, QStyle,
)

from controllers.jv_worker import (
    PIXEL_TO_RELAY_CHANNEL,
    active_pixel_labels,
    default_pixel_area,
    pixel_uses_relay,
)
from instruments.keithley2460 import KEITHLEY_DEFAULT_COMPLIANCE_A
from gui.custom_widgets import NoWheelSpinBox, NoWheelDoubleSpinBox, NoWheelComboBox
from gui.effects import make_panel_shadow, set_glow, update_shadow_color
from gui.style import get_theme_colors

_GLASS_W, _GLASS_H = 110, 190
_TRACE_W, _TRACE_H = 35, 2
_PAD_W, _PAD_H = 10, 6


class JVConfigPanel(RawWidget):
    __slots__ = ('__weakref__',)

    is_dark_mode = d_(Bool(False))

    run_requested = d_(Event(), writable=False)
    layout_changed = d_(Event(), writable=False)
    browse_requested = d_(Event(), writable=False)
    name_changed = d_(Event(), writable=False)
    auto_save_toggled = d_(Event(), writable=False)

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

    _top_layout = Typed(QHBoxLayout)
    _sweep_panel = Typed(QFrame)
    _shadow_widgets = List()

    # Substrate diagram
    _pixel_mode = Typed(NoWheelComboBox)
    _left_pads_layout = Typed(QVBoxLayout)
    _right_pads_layout = Typed(QVBoxLayout)
    _glass_slide_widget = Typed(QFrame)
    _pad_buttons = Value()        # {pin: QPushButton}
    _trace_widgets = Value()      # {pin: QFrame}
    _pixel_pad_widgets = Value()  # {pin: QFrame}

    _pin_active = Value()      # {pin: bool}
    _pin_areas = Value()       # {pin: float}
    _pin_overrides = Value()   # {pin: bool}
    _default_area = Value(0.0396)
    _selected_pin = Value(None)

    # Properties inspector bar
    _inspector_title_lbl = Typed(QLabel)
    _inspector_action_layout = Typed(QHBoxLayout)
    _inspector_main_layout = Typed(QHBoxLayout)

    # Dataset card: Name field, browse icon button, auto-save toggle + path preview
    _name_field = Typed(QLineEdit)
    _auto_save_checkbox = Typed(QCheckBox)
    _path_preview = Typed(QLabel)

    def create_widget(self, parent):
        container = QWidget(parent)

        self._pad_buttons = {}
        self._trace_widgets = {}
        self._pixel_pad_widgets = {}
        self._pin_active = {}
        self._pin_areas = {}
        self._pin_overrides = {}

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

    # --- Substrate diagram ---

    def _build_pixel_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        title_lbl = QLabel("SUBSTRATE")
        title_lbl.setObjectName("PanelTitle")
        header_row.addWidget(title_lbl, 1)

        self._pixel_mode = NoWheelComboBox()
        self._pixel_mode.setMinimumWidth(110)
        self._pixel_mode.addItems(["6 Pixels", "12 Pixels", "Custom"])
        self._pixel_mode.currentIndexChanged.connect(self._on_mode_changed)
        header_row.addWidget(self._pixel_mode)
        layout.addLayout(header_row)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        hybrid_container = QVBoxLayout()
        hybrid_container.setSpacing(15)
        hybrid_container.setAlignment(Qt.AlignHCenter)

        glass_row = QHBoxLayout()
        glass_row.setSpacing(10)
        glass_row.setAlignment(Qt.AlignHCenter)

        self._left_pads_layout = QVBoxLayout()
        self._left_pads_layout.setSpacing(6)
        left_wrap = QWidget()
        left_wrap.setObjectName("PadColumn")
        left_wrap.setAttribute(Qt.WA_StyledBackground, True)
        left_wrap.setLayout(self._left_pads_layout)
        glass_row.addWidget(left_wrap)

        self._glass_slide_widget = QFrame()
        self._glass_slide_widget.setObjectName("GlassSlide")
        self._glass_slide_widget.setAttribute(Qt.WA_StyledBackground, True)
        self._glass_slide_widget.setFixedSize(_GLASS_W, _GLASS_H)
        glass_row.addWidget(self._glass_slide_widget)

        self._right_pads_layout = QVBoxLayout()
        self._right_pads_layout.setSpacing(6)
        right_wrap = QWidget()
        right_wrap.setObjectName("PadColumn")
        right_wrap.setAttribute(Qt.WA_StyledBackground, True)
        right_wrap.setLayout(self._right_pads_layout)
        glass_row.addWidget(right_wrap)

        hybrid_container.addLayout(glass_row)
        hybrid_container.addWidget(self._build_inspector_bar())
        layout.addLayout(hybrid_container)
        layout.addStretch(1)

        layout.addWidget(self._build_dataset_card())

        self._render_layout()

        self._add_shadow(panel)
        return panel

    def _build_inspector_bar(self):
        bar = QFrame()
        bar.setObjectName("InspectorBar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(6)

        top_row = QHBoxLayout()
        self._inspector_title_lbl = QLabel("GLOBAL BATCH DEFAULT")
        self._inspector_title_lbl.setObjectName("InspectorTitle")
        top_row.addWidget(self._inspector_title_lbl)
        top_row.addStretch(1)
        self._inspector_action_layout = QHBoxLayout()
        top_row.addLayout(self._inspector_action_layout)
        outer.addLayout(top_row)

        self._inspector_main_layout = QHBoxLayout()
        outer.addLayout(self._inspector_main_layout)

        return bar

    def _on_mode_changed(self):
        self._selected_pin = None
        self._render_layout()

    def _current_pin_lists(self):
        """Returns (left_pins, right_pins) for the current mode. Custom
        mode is a single directly-wired pixel (no relay) -- shown as one
        pad in the left column, right column empty."""
        mode = self._pixel_mode.currentText()
        labels = active_pixel_labels(mode)
        if mode == "Custom":
            return labels, []
        return labels[0::2], labels[1::2]

    def _render_layout(self):
        """Rebuilds pad buttons + glass-slide trace/marker widgets from
        scratch for the current mode. Mirrors the mockup's renderLayout()."""
        self._clear_layout(self._left_pads_layout)
        self._clear_layout(self._right_pads_layout)
        for child in list(self._glass_slide_widget.children()):
            if isinstance(child, QWidget):
                child.deleteLater()

        left_pins, right_pins = self._current_pin_lists()
        self._default_area = default_pixel_area(self._pixel_mode.currentText())

        # Mode switch resets every visible pin to a fresh state at the new
        # mode's real default area -- see module docstring for why this
        # deliberately doesn't carry over stale state the way the mockup's
        # single-hardcoded-area demo did.
        for pin in left_pins + right_pins:
            self._pin_active[pin] = True
            self._pin_areas[pin] = self._default_area
            self._pin_overrides[pin] = False

        self._pad_buttons = {}
        self._trace_widgets = {}
        self._pixel_pad_widgets = {}

        for pin in left_pins:
            self._left_pads_layout.addWidget(self._create_pad_btn(pin))
        for pin in right_pins:
            self._right_pads_layout.addWidget(self._create_pad_btn(pin))

        for i, pin in enumerate(left_pins):
            self._add_visual_elements(pin, i, len(left_pins), is_left=True)
        for i, pin in enumerate(right_pins):
            self._add_visual_elements(pin, i, len(right_pins), is_left=False)

        self._update_inspector()
        self.layout_changed = True

    @staticmethod
    def _clear_layout(layout):
        # deleteLater(), not setParent(None) -- see _build_pixels()'s old
        # docstring note (still true, same PySide6/Shiboken double-free
        # risk when a widget's last Python reference drops in the same GC
        # pass as its parent's).
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _create_pad_btn(self, pin):
        btn = QPushButton(pin)
        btn.setObjectName("PadBtn")
        btn.setFixedSize(38, 24)
        btn.setProperty("state", "active" if self._pin_active.get(pin) else "inactive")
        self._repolish(btn)
        btn.clicked.connect(functools.partial(self._select_pin, pin))
        self._pad_buttons[pin] = btn
        return btn

    def _add_visual_elements(self, pin, index, total, is_left):
        step = _GLASS_H / (total + 1)
        top_y = int((index + 1) * step)
        is_active = self._pin_active.get(pin)
        accent = get_theme_colors(self.is_dark_mode)["accent"]

        trace = QFrame(self._glass_slide_widget)
        trace.setObjectName("Trace")
        trace.setProperty("state", "active" if is_active else "inactive")
        trace.setGeometry(0 if is_left else _GLASS_W - _TRACE_W, top_y, _TRACE_W, _TRACE_H)
        self._repolish(trace)  # same creation-time repolish requirement as pad buttons
        set_glow(trace, accent, is_active, blur_radius=6)
        trace.show()
        self._trace_widgets[pin] = trace

        pad = QFrame(self._glass_slide_widget)
        pad.setObjectName("PixelPad")
        pad.setProperty("state", "active" if is_active else "inactive")
        pad.setGeometry(
            _TRACE_W if is_left else _GLASS_W - _TRACE_W - _PAD_W,
            top_y - _PAD_H // 2, _PAD_W, _PAD_H,
        )
        self._repolish(pad)
        set_glow(pad, accent, is_active, blur_radius=8)
        pad.show()
        self._pixel_pad_widgets[pin] = pad

    def _select_pin(self, pin):
        if self._selected_pin == pin:
            return
        self._selected_pin = pin
        for p, btn in self._pad_buttons.items():
            btn.setProperty("state", "selected" if p == pin else ("active" if self._pin_active.get(p) else "inactive"))
            self._repolish(btn)
        self._update_inspector()
        self.layout_changed = True

    def _deselect_pin(self):
        self._selected_pin = None
        for p, btn in self._pad_buttons.items():
            btn.setProperty("state", "active" if self._pin_active.get(p) else "inactive")
            self._repolish(btn)
        self._update_inspector()
        self.layout_changed = True

    @staticmethod
    def _repolish(widget):
        # setProperty() alone doesn't retroactively re-resolve an
        # attribute-selector QSS rule for an already-polished widget --
        # confirmed by testing (see header_panel.enaml's post_activate_setup
        # for the full story). unpolish+polish forces the re-resolution.
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _update_inspector(self):
        self._clear_layout(self._inspector_action_layout)
        self._clear_layout(self._inspector_main_layout)

        if self._selected_pin is None:
            self._inspector_title_lbl.setText("GLOBAL BATCH DEFAULT")

            hint = QLabel("Click a pin above to inspect.")
            hint.setObjectName("DimLabel")
            hint.setStyleSheet("font-size: 7.5pt;")
            self._inspector_action_layout.addWidget(hint)

            lbl = QLabel("Batch Area:")
            lbl.setObjectName("DimLabel")
            self._inspector_main_layout.addWidget(lbl)
            self._inspector_main_layout.addStretch(1)

            area_input = NoWheelDoubleSpinBox()
            area_input.setRange(0.0001, 100)
            area_input.setDecimals(4)
            area_input.setValue(self._default_area)
            area_input.setFixedWidth(90)
            area_input.valueChanged.connect(self._on_area_input_changed)
            self._inspector_main_layout.addWidget(area_input)

            unit_lbl = QLabel("cm\u00b2")
            unit_lbl.setObjectName("DimLabel")
            self._inspector_main_layout.addWidget(unit_lbl)
        else:
            pin = self._selected_pin
            self._inspector_title_lbl.setText(f"PIN {pin} PROPERTIES")

            close_btn = QPushButton("\u2715")
            close_btn.setObjectName("CloseInspectorBtn")
            close_btn.setToolTip("Return to global settings")
            close_btn.clicked.connect(self._deselect_pin)
            self._inspector_action_layout.addWidget(close_btn)

            active_check = QCheckBox("Active")
            active_check.setChecked(bool(self._pin_active.get(pin)))
            active_check.toggled.connect(functools.partial(self._toggle_pin_active, pin))
            self._inspector_main_layout.addWidget(active_check)
            self._inspector_main_layout.addStretch(1)

            override_check = QCheckBox("Override")
            override_check.setChecked(bool(self._pin_overrides.get(pin)))
            override_check.toggled.connect(functools.partial(self._toggle_override, pin))
            self._inspector_main_layout.addWidget(override_check)

            is_override = bool(self._pin_overrides.get(pin))
            area_input = NoWheelDoubleSpinBox()
            area_input.setRange(0.0001, 100)
            area_input.setDecimals(4)
            area_input.setValue(self._pin_areas.get(pin, self._default_area) if is_override else self._default_area)
            area_input.setEnabled(is_override)
            area_input.setFixedWidth(90)
            area_input.valueChanged.connect(self._on_area_input_changed)
            self._inspector_main_layout.addWidget(area_input)

            unit_lbl = QLabel("cm\u00b2")
            unit_lbl.setObjectName("DimLabel")
            self._inspector_main_layout.addWidget(unit_lbl)

    def _toggle_pin_active(self, pin, checked):
        self._pin_active[pin] = checked

        btn = self._pad_buttons.get(pin)
        if btn is not None:
            btn.setProperty("state", "selected" if self._selected_pin == pin else ("active" if checked else "inactive"))
            self._repolish(btn)

        for widgets in (self._trace_widgets, self._pixel_pad_widgets):
            w = widgets.get(pin)
            if w is not None:
                w.setProperty("state", "active" if checked else "inactive")
                self._repolish(w)
                accent = get_theme_colors(self.is_dark_mode)["accent"]
                set_glow(w, accent, checked, blur_radius=6 if widgets is self._trace_widgets else 8)

        self.layout_changed = True

    def _toggle_override(self, pin, checked):
        self._pin_overrides[pin] = checked
        if not checked:
            self._pin_areas[pin] = self._default_area
        self._update_inspector()
        self.layout_changed = True

    def _on_area_input_changed(self, value):
        if self._selected_pin is None:
            self._default_area = value
            for pin, overridden in self._pin_overrides.items():
                if not overridden:
                    self._pin_areas[pin] = value
        else:
            if self._pin_overrides.get(self._selected_pin):
                self._pin_areas[self._selected_pin] = value
        self.layout_changed = True

    # --- Dataset card: relocated from the old header (Name/Browse), plus
    # the new Enable Auto-Save toggle and its live path preview ---

    def _build_dataset_card(self):
        card = QFrame()
        card.setObjectName("DatasetCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        name_lbl = QLabel("Name:")
        name_lbl.setObjectName("DimLabel")
        name_lbl.setFixedWidth(45)
        name_row.addWidget(name_lbl)

        self._name_field = QLineEdit("Sample_A")
        self._name_field.textChanged.connect(self._on_name_changed)
        name_row.addWidget(self._name_field, 1)

        browse_btn = QPushButton()
        # Standard Qt icon (maybe needs modification b/c Linux)
        browse_btn.setIcon(browse_btn.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        browse_btn.setFixedSize(34, 34)
        browse_btn.clicked.connect(self._on_browse_clicked)
        name_row.addWidget(browse_btn)
        layout.addLayout(name_row)

        self._auto_save_checkbox = QCheckBox("Enable Auto-Save")
        self._auto_save_checkbox.setChecked(True)
        self._auto_save_checkbox.toggled.connect(self._on_auto_save_toggled)
        layout.addWidget(self._auto_save_checkbox)

        self._path_preview = QLabel("")
        self._path_preview.setObjectName("PathPreview")
        self._path_preview.setAttribute(Qt.WA_StyledBackground, True)
        self._path_preview.setWordWrap(True)
        layout.addWidget(self._path_preview)

        return card

    def _on_name_changed(self, text):
        self.name_changed = True

    def _on_browse_clicked(self):
        self.browse_requested = True

    def _on_auto_save_toggled(self, checked):
        self.auto_save_toggled = True

    def _add_shadow(self, widget):
        effect = make_panel_shadow(widget, self.is_dark_mode)
        self._shadow_widgets = self._shadow_widgets + [effect]

    # --- Public API for the controller ---

    def refresh_layout(self, available_width=None):
        """available_width is accepted-but-unused: kept for interface
        compatibility"""
        widget = self.get_widget()
        if widget is not None:
            widget.updateGeometry()

    def validate(self):
        """Panel-local validation only (voltage range, pixel selection).
        Instrument-connection validation is the controller's job."""
        if self._v0.value() == self._v1.value():
            return "ERROR: Start and Stop voltage cannot be the same."
        if not any(self._pin_active.values()):
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
        left_pins, right_pins = self._current_pin_lists()
        selected = []
        for pin in left_pins + right_pins:
            if self._pin_active.get(pin):
                channel = PIXEL_TO_RELAY_CHANNEL[pin] if use_relay else None
                selected.append((pin, channel, self._pin_areas.get(pin, self._default_area)))
        return selected

    def set_running(self, running):
        self._start_btn.setEnabled(not running)
        self._name_field.setEnabled(not running)
        self._auto_save_checkbox.setEnabled(not running)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        for effect in self._shadow_widgets:
            update_shadow_color(effect, is_dark_mode)
        # Static QSS (style.py)| theme change is handled by the global
        # stylesheet cascade, yet explict repolish per defense.
        for widgets in (self._pad_buttons, self._trace_widgets, self._pixel_pad_widgets):
            for w in widgets.values():
                self._repolish(w)
        accent = colors["accent"]
        for pin, trace in self._trace_widgets.items():
            set_glow(trace, accent, bool(self._pin_active.get(pin)), blur_radius=6)
        for pin, pad in self._pixel_pad_widgets.items():
            set_glow(pad, accent, bool(self._pin_active.get(pin)), blur_radius=8)

    def sample_name(self):
        return self._name_field.text().strip()

    def auto_save_enabled(self):
        return self._auto_save_checkbox.isChecked()

    def set_path_preview(self, text, is_warning):
        self._path_preview.setText(text)
        self._path_preview.setProperty("state", "warning" if is_warning else "")
        self._repolish(self._path_preview)
