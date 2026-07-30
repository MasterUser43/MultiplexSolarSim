"""
System event log panel. Owns the log text widget, the
save-directory display, and its own TXT export/clear actions.

This is a RawWidget wrapper around a plain PySide6 widget tree, not an
enamldef given that log_message()/_retheme_log() do direct QTextCursor/
QTextCharFormat manipulation to tag and recolor individual text runs by
severity, which doesn't have a declarative-markup equivalent in Enaml.
"""
import os
import time

from atom.api import Bool, Str, Typed, Value
from enaml.core.declarative import d_
from enaml.widgets.raw_widget import RawWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCursor, QTextCharFormat, QTextFormat
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit,
)

from core.paths import get_logs_dir
from gui.effects import make_panel_shadow, update_shadow_color
from gui.style import get_theme_colors

# Custom QTextFormat property ID used to tag each log run with its
# semantic color role (e.g. "text_dim", "warning")
_LOG_ROLE_PROPERTY = QTextFormat.UserProperty + 1


class LogPanel(RawWidget):
    __slots__ = ('__weakref__',)

    output_dir = d_(Str())
    is_dark_mode = d_(Bool(False))

    _log = Typed(QTextEdit)
    _output_dir_field = Typed(QLineEdit)
    _shadow = Value()  # QGraphicsDropShadowEffect, from make_panel_shadow()

    def create_widget(self, parent):
        card = QFrame(parent)
        card.setObjectName("PanelContainer")
        card.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title_lbl = QLabel("SYSTEM EVENT LOG")
        title_lbl.setObjectName("PanelTitleLarge")
        layout.addWidget(title_lbl)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        self._log = QTextEdit()
        self._log.setReadOnly(True)

        top = QHBoxLayout()

        save_dir_lbl = QLabel("Save Directory:")
        save_dir_lbl.setObjectName("DimLabel")
        top.addWidget(save_dir_lbl)
        self._output_dir_field = QLineEdit(self.output_dir)
        self._output_dir_field.setReadOnly(True)
        top.addWidget(self._output_dir_field, 1)

        export_log_btn = QPushButton("Export .TXT")
        export_log_btn.clicked.connect(self.export_log_data)
        top.addWidget(export_log_btn)

        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.clicked.connect(self._log.clear)
        top.addWidget(clear_log_btn)

        layout.addLayout(top)
        layout.addWidget(self._log)

        self._shadow = make_panel_shadow(card, self.is_dark_mode)

        return card

    # --- Public API  ---

    def set_output_dir(self, path):
        self.output_dir = path
        if self._output_dir_field is not None:
            self._output_dir_field.setText(path)

    def log_message(self, message):
        stamp = time.strftime("%H:%M:%S")
        colors = get_theme_colors(self.is_dark_mode)

        # Each log line renders as `[ts] PREFIX: rest`, w/ the prefix (and,
        # for WARNING/ERROR, the whole line) tinted by severity
        prefix, sep, rest = message.partition(": ")
        prefix_key = prefix.strip().upper()

        severity_roles = {
            "OK": ("success", "text_main"),
            "WARNING": ("warning", "warning"),
            "ERROR": ("error", "error"),
        }

        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.End)
        if self._log.toPlainText():
            cursor.insertBlock()

        def write(text, role, bold=False):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colors[role]))
            fmt.setProperty(_LOG_ROLE_PROPERTY, role)
            if bold:
                fmt.setFontWeight(QFont.Bold)
            cursor.setCharFormat(fmt)
            cursor.insertText(text)

        write(f"[{stamp}] ", "text_dim")

        if sep and prefix_key in severity_roles:
            prefix_role, text_role = severity_roles[prefix_key]
            write(f"{prefix}: ", prefix_role, bold=True)
            write(rest, text_role)
        else:
            write(message, "text_main")

        self._log.setTextCursor(cursor)
        self._log.moveCursor(QTextCursor.End)  # Auto-scroll
        QApplication.processEvents()

    def export_log_data(self):
        log_text = self._log.toPlainText()
        if not log_text.strip():
            self.log_message("WARNING: Log is empty, nothing to export.")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"System_Log_{timestamp}.txt"
        path = os.path.join(get_logs_dir(), filename)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(log_text)
            self.log_message(f"OK: Log successfully exported to {path}")
        except Exception as e:
            self.log_message(f"ERROR: Could not export log file: {e}")

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        update_shadow_color(self._shadow, is_dark_mode)
        self._retheme_log(colors)

    def _retheme_log(self, colors):
        """Walks the log's existing text runs in place and updates each
        one's color from its tagged role, using the current theme."""
        doc = self._log.document()

        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    role = frag.charFormat().property(_LOG_ROLE_PROPERTY)
                    if role in colors:
                        run_cursor = QTextCursor(doc)
                        run_cursor.setPosition(frag.position())
                        run_cursor.setPosition(frag.position() + frag.length(), QTextCursor.KeepAnchor)

                        # mergeCharFormat only touches the properties set here
                        # (foreground + role tag)
                        recolor_fmt = QTextCharFormat()
                        recolor_fmt.setForeground(QColor(colors[role]))
                        recolor_fmt.setProperty(_LOG_ROLE_PROPERTY, role)
                        run_cursor.mergeCharFormat(recolor_fmt)
                it += 1
            block = block.next()
