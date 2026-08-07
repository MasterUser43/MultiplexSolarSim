"""
Top header bar: brand title, Keithley/Relay status LEDs, connect button,
and the theme toggle.

Plain Atom object + imperative PySide6 layout, not Enaml given uncomptability.
Instead, simply focus on atom stuff.

Qt-facing signals (connect_clicked/theme_toggled) are plain Atom Events;
controllers use `.observe(...)`.
"""
from atom.api import Atom, Bool, Event, Typed
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from gui.effects import refresh_led_glow, set_status_led


class HeaderPanel(Atom):
    __slots__ = ('__weakref__',)

    is_dark_mode = Bool(False)

    connect_clicked = Event()
    theme_toggled = Event()

    _widget = Typed(QWidget)
    _brand_title = Typed(QLabel)
    _keithley_led = Typed(QLabel)
    _keithley_lbl = Typed(QLabel)
    _relay_led = Typed(QLabel)
    _relay_lbl = Typed(QLabel)
    _connect_btn = Typed(QPushButton)
    _theme_btn = Typed(QPushButton)

    def get_widget(self):
        return self._widget

    def create_widget(self, parent):
        container = QWidget(parent)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(10)

        self._brand_title = QLabel("MULTIPLEX SIM")
        self._brand_title.setObjectName("BrandTitle")
        layout.addWidget(self._brand_title, 0, Qt.AlignVCenter)

        self._keithley_led = QLabel("")
        self._keithley_led.setObjectName("StatusLED")
        self._keithley_led.setAttribute(Qt.WA_StyledBackground, True)
        layout.addWidget(self._keithley_led, 0, Qt.AlignVCenter)

        self._keithley_lbl = QLabel("KEITHLEY\n2460")
        self._keithley_lbl.setObjectName("StatusLabel")
        layout.addWidget(self._keithley_lbl, 0, Qt.AlignVCenter)

        self._relay_led = QLabel("")
        self._relay_led.setObjectName("StatusLED")
        self._relay_led.setAttribute(Qt.WA_StyledBackground, True)
        layout.addWidget(self._relay_led, 0, Qt.AlignVCenter)

        self._relay_lbl = QLabel("RELAY\nMATRIX")
        self._relay_lbl.setObjectName("StatusLabel")
        layout.addWidget(self._relay_lbl, 0, Qt.AlignVCenter)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self._connect_btn, 0, Qt.AlignVCenter)

        layout.addStretch(1)

        self._theme_btn = QPushButton("\u2600\ufe0f" if self.is_dark_mode else "\U0001F319")
        self._theme_btn.setObjectName("ThemeButton")
        self._theme_btn.clicked.connect(self._on_theme_clicked)
        layout.addWidget(self._theme_btn, 0, Qt.AlignVCenter)

        set_status_led(self._keithley_led, self._keithley_lbl, "idle")
        set_status_led(self._relay_led, self._relay_lbl, "idle")

        self._widget = container
        return container

    def _on_connect_clicked(self):
        self.connect_clicked = True

    def _on_theme_clicked(self):
        self.theme_toggled = True

    # --- Public API (unchanged names/signatures from the old QFrame/enaml versions) ---

    def set_connection_status(self, keithley_ok, relay_ok, colors):
        set_status_led(self._keithley_led, self._keithley_lbl, "ok" if keithley_ok else "bad")
        set_status_led(self._relay_led, self._relay_lbl, "ok" if relay_ok else "bad")
        refresh_led_glow(self._keithley_led, colors)
        refresh_led_glow(self._relay_led, colors)
        self._connect_btn.setText("Reconnect")

    def set_running(self, running):
        self._connect_btn.setEnabled(not running)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        self._theme_btn.setText("\u2600\ufe0f" if is_dark_mode else "\U0001F319")
        refresh_led_glow(self._keithley_led, colors)
        refresh_led_glow(self._relay_led, colors)
