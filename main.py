"""
Entry point: initializes the Qt application, sets pyqtgraph options, and
opens the main window.
"""
import sys

import pyqtgraph as pg
from PyQt5.QtWidgets import QApplication

from gui.app_window import GUI


def main():
    app = QApplication(sys.argv)
    pg.setConfigOptions(antialias=True)
    window = GUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
