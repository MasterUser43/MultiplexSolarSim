"""
Entry point.

Two-stage startup so a slow lab laptop shows something alive within ~1
second

  1. Create the QApplication and a lightweight QSplashScreen (gui.splash)
     built only from PySide6 + gui.style, both cheap/already-needed
     imports (no numpy/scipy/pyqtgraph yet).
  2. Show the splash and flush the event loop so it actually paints.
  3. Then import the heavy modules (pyqtgraph, gui.main_window, which
     pulls in the controllers/core/instruments stack) and build the real
     window.
  4. Swap the splash for the main window.

Progress bars and pip errors are visible in a real terminal b/f this GUI process
(run windowed, via pythonw) ever starts.
"""
import sys


def main():
    from PySide6.QtWidgets import QApplication
    from gui.splash import build_splash, splash_message

    mock = "--mock" in sys.argv

    app = QApplication(sys.argv)

    # --- Stage 1: splash appears before any heavy imports ---
    splash = build_splash(app)
    splash_message(splash, "Starting up...")
    splash.show()
    app.processEvents()

    # --- Stage 2: heavy imports happen only now ---
    splash_message(splash, "Loading numerical libraries...")
    app.processEvents()
    import pyqtgraph as pg

    splash_message(splash, "Building interface...")
    app.processEvents()
    from gui.main_window import MainWindow

    pg.setConfigOptions(antialias=True)
    window = MainWindow(mock=mock)

    splash.finish(window)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
