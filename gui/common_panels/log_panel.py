"""
System event log panel. Owns the log text widget, the 
save-directory display, and its own TXT export/clear actions.
"""
import os
import time

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QTextCursor, QTextCharFormat, QTextFormat
from PyQt5.QtWidgets import (
    QApplication, QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit,
)

from gui.effects import make_panel_shadow, update_shadow_color
from gui.style import get_theme_colors

# Custom QTextFormat property ID used to tag each log run with its
# semantic color role (e.g. "text_dim", "warning")
_LOG_ROLE_PROPERTY = QTextFormat.UserProperty + 1


class LogPanel(QWidget):
    """Because Qt limits each widget to one graphics effect, 
    the tab-switch animation and the card's shadow cannot share the same widget.
    """

    def __init__(self, output_dir, is_dark_mode=False, parent=None):
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.output_dir = output_dir

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QFrame()
        self._card.setObjectName("PanelContainer")
        self._card.setAttribute(Qt.WA_StyledBackground, True)
        outer.addWidget(self._card)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title_lbl = QLabel("SYSTEM EVENT LOG")
        title_lbl.setObjectName("PanelTitleLarge")
        layout.addWidget(title_lbl)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        top = QHBoxLayout()

        save_dir_lbl = QLabel("Save Directory:")
        save_dir_lbl.setObjectName("DimLabel")
        top.addWidget(save_dir_lbl)
        self.output_dir_field = QLineEdit(self.output_dir)
        self.output_dir_field.setReadOnly(True)
        top.addWidget(self.output_dir_field, 1)

        self.export_log_btn = QPushButton("Export .TXT")
        self.export_log_btn.clicked.connect(self.export_log_data)
        top.addWidget(self.export_log_btn)

        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.log.clear)
        top.addWidget(self.clear_log_btn)

        layout.addLayout(top)
        layout.addWidget(self.log)

        self._shadow = make_panel_shadow(self._card, self.is_dark_mode)

    # --- Public API ---

    def set_output_dir(self, path):
        self.output_dir = path
        self.output_dir_field.setText(path)

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

        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.End)
        if self.log.toPlainText():
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

        self.log.setTextCursor(cursor)
        self.log.moveCursor(QTextCursor.End)  # Auto-scroll
        QApplication.processEvents()

    def export_log_data(self):
        log_text = self.log.toPlainText()
        if not log_text.strip():
            self.log_message("WARNING: Log is empty, nothing to export.")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"System_Log_{timestamp}.txt"
        path = os.path.join(self.output_dir, filename)

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
        doc = self.log.document()

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
