"""
Startup splash screen.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QSplashScreen

from gui.style import THEME_COLORS

_COLORS = THEME_COLORS[True]  # dark mode
_WIDTH, _HEIGHT = 460, 260


def build_splash(app):
    pix = QPixmap(_WIDTH, _HEIGHT)
    pix.fill(QColor(_COLORS["bg_base"]))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    # Accent bar
    painter.setBrush(QColor(_COLORS["accent"]))
    painter.setPen(Qt.NoPen)
    painter.drawRect(0, 0, _WIDTH, 6)

    # Title
    title_font = QFont("Segoe UI", 18, QFont.Bold)
    painter.setFont(title_font)
    painter.setPen(QColor(_COLORS["text_main"]))
    painter.drawText(pix.rect().adjusted(0, 40, 0, 0), Qt.AlignHCenter | Qt.AlignTop, "MULTIPLEX SIM")

    subtitle_font = QFont("Segoe UI", 10)
    painter.setFont(subtitle_font)
    painter.setPen(QColor(_COLORS["text_dim"]))
    painter.drawText(
        pix.rect().adjusted(0, 78, 0, 0),
        Qt.AlignHCenter | Qt.AlignTop,
        "Solar Cell IV Characterization",
    )
    painter.end()

    splash = QSplashScreen(pix, Qt.WindowStaysOnTopHint)
    splash.setWindowFlag(Qt.FramelessWindowHint)
    return splash


def splash_message(splash, text):
    splash.showMessage(text, Qt.AlignHCenter | Qt.AlignBottom, QColor(_COLORS["accent"]))
