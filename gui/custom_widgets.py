"""
Small, generic PyQt/pyqtgraph widget overrides with no business logic.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSpinBox, QDoubleSpinBox, QComboBox
import pyqtgraph as pg


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelViewBox(pg.ViewBox):
    def __init__(self, range_callback=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.range_callback = range_callback

    def wheelEvent(self, event, axis=None):
        event.ignore()

    def mouseClickEvent(self, event):
        if event.button() == Qt.RightButton and self.range_callback:
            event.accept()
            self.range_callback()
            return
        super().mouseClickEvent(event)
