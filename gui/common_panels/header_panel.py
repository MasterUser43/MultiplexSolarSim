"""
Top header bar: brand title, Keithley/Relay status LEDs, connect button,
sample ID field, output-folder browse button, and the theme toggle.
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QFontMetrics
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy

from gui.effects import set_status_led, refresh_led_glow


class HeaderPanel(QFrame):
    connect_clicked = pyqtSignal()
    browse_clicked = pyqtSignal()
    theme_toggled = pyqtSignal()

    def __init__(self, is_dark_mode=False, parent=None):
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.setObjectName("Header")
        self.setFixedHeight(76)

        layout = QHBoxLayout(self)
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
        self.connect_btn.clicked.connect(self.connect_clicked.emit)
        layout.addWidget(self.connect_btn)

        layout.addStretch(1)

        # Right Side Inputs (Sample ID & Browse)
        self.sample_lbl = QLabel("Sample ID:")
        self.sample_lbl.setObjectName("DimLabel")
        layout.addWidget(self.sample_lbl)

        self.sample_id_field = QLineEdit("Sample_Batch_01")
        self.sample_id_field.setMinimumWidth(220)
        self.sample_id_field.setMaximumWidth(340)
        self.sample_id_field.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.sample_id_field.setMinimumHeight(32)
        layout.addWidget(self.sample_id_field)

        self.browse_dir_btn = QPushButton("Browse...")
        self.browse_dir_btn.setObjectName("PrimaryButton")
        self.browse_dir_btn.setMinimumHeight(32)
        self.browse_dir_btn.clicked.connect(self.browse_clicked.emit)
        layout.addWidget(self.browse_dir_btn)

        # Theme Toggle
        self.theme_btn = QPushButton("\u2600\ufe0f" if self.is_dark_mode else "\U0001F319")
        self.theme_btn.setObjectName("ThemeButton")
        self.theme_btn.setFixedSize(36, 36)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(self.theme_toggled.emit)
        layout.addWidget(self.theme_btn)

    # --- Public API for controllers ---

    def sample_name(self):
        return self.sample_id_field.text().strip()

    def set_connection_status(self, keithley_ok, relay_ok, colors):
        set_status_led(self.keithley_led, self.keithley_lbl, "ok" if keithley_ok else "bad")
        set_status_led(self.relay_led, self.relay_lbl, "ok" if relay_ok else "bad")
        refresh_led_glow(self.keithley_led, colors)
        refresh_led_glow(self.relay_led, colors)
        self.connect_btn.setText("Reconnect")

    def set_running(self, running):
        self.connect_btn.setEnabled(not running)
        self.browse_dir_btn.setEnabled(not running)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        self.theme_btn.setText("\u2600\ufe0f" if is_dark_mode else "\U0001F319")
        for w in (self.keithley_led, self.keithley_lbl, self.relay_led, self.relay_lbl):
            w.style().unpolish(w)
            w.style().polish(w)
        refresh_led_glow(self.keithley_led, colors)
        refresh_led_glow(self.relay_led, colors)
