"""
Small, generic PyQt/pyqtgraph widget overrides with no business logic.
"""
from PyQt5.QtCore import Qt, QRectF, QSize
from PyQt5.QtGui import QTextDocument, QFont, QFontMetrics
from PyQt5.QtWidgets import QSpinBox, QDoubleSpinBox, QComboBox, QHeaderView, QStyle, QStyleOptionHeader, QTabBar
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


class RichTextHeaderView(QHeaderView):
    """A QHeaderView that renders section labels as HTML instead of plain
    text. Useful for subscript labelling."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setDefaultAlignment(Qt.AlignCenter)
        self._text_color = "#000000"

    def set_text_color(self, hex_color):
        self._text_color = hex_color
        self.viewport().update()

    def paintSection(self, painter, rect, logical_index):
        painter.save()

        # Draw the normal header chrome (background/border) w/o text
        opt = self._style_option(logical_index, rect)
        opt.text = ""
        self.style().drawControl(QStyle.CE_Header, opt, painter, self)

        text = self.model().headerData(logical_index, self.orientation(), Qt.DisplayRole)
        if text:
            doc = QTextDocument()
            doc.setDefaultFont(self.font())
            doc.setHtml(
                f'<div align="center" style="color:{self._text_color}; font-weight:bold;">{text}</div>'
            )
            doc.setTextWidth(rect.width())

            doc_height = doc.size().height()
            y_offset = max(0, (rect.height() - doc_height) / 2)

            painter.translate(rect.left(), rect.top() + y_offset)
            doc.drawContents(painter, QRectF(0, 0, rect.width(), rect.height()))

        painter.restore()

    def _style_option(self, logical_index, rect):
        opt = QStyleOptionHeader()
        self.initStyleOption(opt)
        opt.rect = rect
        opt.section = logical_index
        return opt

    def sectionSizeHint(self, logical_index):
        size = super().sectionSizeHint(logical_index)
        return QSize(size.width(), max(size.height(), 34))

    def sectionSizeFromContents(self, logical_index):
        """`ResizeToContents` calls this (not sectionSizeHint) to size each
        column. Prevents super-wide columns
        """
        text = self.model().headerData(logical_index, self.orientation(), Qt.DisplayRole) if self.model() else None
        if not text:
            return super().sectionSizeFromContents(logical_index)

        doc = QTextDocument()
        doc.setDefaultFont(self.font())
        doc.setHtml(f'<div style="font-weight:bold; white-space:nowrap;">{text}</div>')
        doc.setTextWidth(-1)  # natural, unconstrained width

        width = int(doc.idealWidth()) + 24  # horizontal padding
        height = max(int(doc.size().height()) + 14, 34)
        return QSize(width, height)


class SafeTabBar(QTabBar):
    """This computes the needed width directly from real font metrics"""

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)

        bold_font = QFont(self.font())
        bold_font.setBold(True)
        text_width = QFontMetrics(bold_font).horizontalAdvance(self.tabText(index))

        # Matches the QSS `padding: 12px 28px` (56px total horizontal) plus
        # a small safety margin.
        needed_width = text_width + 64
        needed_height = max(size.height(), 46)
        return QSize(max(size.width(), needed_width), needed_height)
