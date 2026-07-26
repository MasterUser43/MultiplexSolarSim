"""
JV "RESULTS" tab: the extracted-metrics table and its Export .TXT / Export
.CSV buttons.
"""
import numpy as np
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
)

from gui.custom_widgets import RichTextHeaderView
from gui.formatting import format_metric, format_resistance
from gui.effects import make_panel_shadow, update_shadow_color
from gui.style import get_theme_colors

# Column indices for the diode-model fit values (Rs fit / Rsh fit).
_FIT_CELL_COLUMNS = {10, 11}

_HEADERS = [
    "Loop", "Pixel", "Area", "V<sub>oc</sub> (V)", "J<sub>sc</sub> (mA/cm\u00b2)", "FF",
    "PCE (%)", "V<sub>mpp</sub> (V)", "J<sub>mpp</sub> (mA/cm\u00b2)", "P<sub>max</sub> (mW/cm\u00b2)",
    "R<sub>s</sub> fit (\u03a9)", "R<sub>sh</sub> fit (\u03a9)",
    "R<sub>s</sub> deriv (\u03a9)", "R<sub>sh</sub> deriv (\u03a9)",
    "Status",
]


class JVResultsPanel(QWidget):
    export_txt_requested = pyqtSignal()
    export_csv_requested = pyqtSignal()

    def __init__(self, is_dark_mode=False, parent=None):
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self._role_colored_items = []  # [(QTableWidgetItem, role), ...] for theme refresh

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_results_panel())

    def _build_results_panel(self):
        panel = QFrame()
        panel.setObjectName("PanelContainer")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        title_lbl = QLabel("EXTRACTED METRICS")
        title_lbl.setObjectName("PanelTitle")
        header_row.addWidget(title_lbl)
        header_row.addStretch(1)

        export_lbl = QLabel("MANUAL EXPORT:")
        export_lbl.setObjectName("DimLabel")
        header_row.addWidget(export_lbl)

        self.export_txt_btn = QPushButton("Export .TXT")
        self.export_txt_btn.clicked.connect(self.export_txt_requested.emit)
        self.export_txt_btn.setEnabled(False)
        header_row.addWidget(self.export_txt_btn)

        self.export_csv_btn = QPushButton("Export .CSV")
        self.export_csv_btn.clicked.connect(self.export_csv_requested.emit)
        self.export_csv_btn.setEnabled(False)
        header_row.addWidget(self.export_csv_btn)

        layout.addLayout(header_row)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        table_wrap = QFrame()
        table_wrap.setObjectName("TableWrap")
        table_wrap.setAttribute(Qt.WA_StyledBackground, True)
        table_wrap_layout = QVBoxLayout(table_wrap)
        table_wrap_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setObjectName("ResultsTable")
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setColumnCount(len(_HEADERS))

        header = RichTextHeaderView(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(header)
        header.set_text_color(get_theme_colors(self.is_dark_mode)["accent"])

        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(260)
        table_wrap_layout.addWidget(self.table)

        layout.addWidget(table_wrap)

        self._shadow = make_panel_shadow(panel, self.is_dark_mode)
        return panel

    # --- Public API for the controller ---

    def clear(self):
        self.table.setRowCount(0)
        self._role_colored_items = []

    def add_result_row(self, pixel, area, metrics, status, loop_idx=None):
        r = self.table.rowCount()
        self.table.insertRow(r)

        values = [
            f"L{loop_idx}" if loop_idx is not None else "--",
            pixel,
            f"{area:.4f}",
        ]

        if metrics:
            values.extend([
                format_metric(metrics["Voc"], 3),
                format_metric(metrics["Jsc"], 3),
                format_metric(metrics["FF"], 3),
                format_metric(metrics["PCE"], 3),
                format_metric(metrics["Vmpp"], 3),
                format_metric(metrics["Jmpp"], 3),
                format_metric(metrics["Pmax"], 3),
                format_resistance(metrics.get("Rs_diode_eq")),
                format_resistance(metrics.get("Rsh_diode_eq")),
                format_resistance(metrics.get("Rs_derivative")),
                format_resistance(metrics.get("Rsh_derivative")),
            ])
        else:
            values.extend(["--"] * 11)

        values.append(status)

        for col, value in enumerate(values):
            item = QTableWidgetItem(value)

            if col > 0:
                item.setTextAlignment(Qt.AlignCenter)

            if col in _FIT_CELL_COLUMNS and value != "--":
                self._apply_role_color(item, "warning")
                font = item.font()
                font.setItalic(True)
                font.setBold(True)
                item.setFont(font)

            if col == self.table.columnCount() - 1:
                # Status column: green for OK, red for any fault string
                self._apply_role_color(item, "success" if value == "OK" else "error")
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.table.setItem(r, col, item)

    def _apply_role_color(self, item, role):
        item.setForeground(QBrush(QColor(get_theme_colors(self.is_dark_mode)[role])))
        self._role_colored_items.append((item, role))

    def get_export_data(self):
        """Returns (headers, rows) as plain strings, with rich-text markup
        stripped, ready for a CSV writer. Keeps the raw QTableWidget out of
        the controller's hands."""
        headers = []
        for col in range(self.table.columnCount()):
            header_item = self.table.horizontalHeaderItem(col)
            raw = header_item.text() if header_item else ""
            headers.append(raw.replace("<sub>", "").replace("</sub>", ""))

        rows = []
        for r in range(self.table.rowCount()):
            rows.append([
                self.table.item(r, c).text() if self.table.item(r, c) else ""
                for c in range(self.table.columnCount())
            ])
        return headers, rows

    def has_rows(self):
        return self.table.rowCount() > 0

    def set_export_enabled(self, enabled):
        self.export_txt_btn.setEnabled(enabled)
        self.export_csv_btn.setEnabled(enabled)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        update_shadow_color(self._shadow, is_dark_mode)

        for item, role in self._role_colored_items:
            item.setForeground(QBrush(QColor(colors[role])))

        header = self.table.horizontalHeader()
        if isinstance(header, RichTextHeaderView):
            header.set_text_color(colors["accent"])
