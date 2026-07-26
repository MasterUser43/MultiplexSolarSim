"""
Entry point.

Two-stage startup so a slow lab laptop shows something alive within ~1
second

  1. Create the QApplication and a lightweight QSplashScreen using only
     the pieces of PyQt5 that are already imported to build the splash
     itself (no numpy/scipy/pyqtgraph yet).
  2. Show the splash and flush the event loop so it actually paints.
  3. *Then* import the heavy modules (pyqtgraph, gui.main_window, which
     pulls in the controllers/core/instruments stack) and build the real
     window.
  4. Swap the splash for the main window.

Progress bars and pip errors are visible in a real terminal b/f this GUI process
(run windowed, via pythonw) ever starts.
"""
import sys


def _build_splash(app):
    from PyQt5.QtWidgets import QSplashScreen
    from PyQt5.QtGui import QPixmap, QColor, QPainter, QFont
    from PyQt5.QtCore import Qt

    width, height = 460, 260
    pix = QPixmap(width, height)
    pix.fill(QColor("#0b1120"))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    # Accent bar
    painter.setBrush(QColor("#38bdf8"))
    painter.setPen(Qt.NoPen)
    painter.drawRect(0, 0, width, 6)

    # Title
    title_font = QFont("Segoe UI", 18, QFont.Bold)
    painter.setFont(title_font)
    painter.setPen(QColor("#f8fafc"))
    painter.drawText(pix.rect().adjusted(0, 40, 0, 0), Qt.AlignHCenter | Qt.AlignTop, "MULTIPLEX SIM")

    subtitle_font = QFont("Segoe UI", 10)
    painter.setFont(subtitle_font)
    painter.setPen(QColor("#94a3b8"))
    painter.drawText(
        pix.rect().adjusted(0, 78, 0, 0),
        Qt.AlignHCenter | Qt.AlignTop,
        "Solar Cell IV Characterization",
    )
    painter.end()

    splash = QSplashScreen(pix, Qt.WindowStaysOnTopHint)
    splash.setWindowFlag(Qt.FramelessWindowHint)
    return splash


def _splash_message(splash, text):
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor

    splash.showMessage(text, Qt.AlignHCenter | Qt.AlignBottom, QColor("#38bdf8"))


def main():
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # --- Stage 1: splash appears before any heavy imports ---
    splash = _build_splash(app)
    _splash_message(splash, "Starting up...")
    splash.show()
    app.processEvents()

    # --- Stage 2: heavy imports happen only now ---
    _splash_message(splash, "Loading numerical libraries...")
    app.processEvents()
    import pyqtgraph as pg

    _splash_message(splash, "Building interface...")
    app.processEvents()
    from gui.main_window import MainWindow

    pg.setConfigOptions(antialias=True)
    window = MainWindow()

    splash.finish(window)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
