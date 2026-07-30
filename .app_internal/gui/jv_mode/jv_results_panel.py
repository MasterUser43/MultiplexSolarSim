"""
JV "RESULTS" tab: the extracted-metrics table and its Export .TXT / Export
.CSV buttons.
"""
from atom.api import Bool, Event, List, Typed
from enaml.core.declarative import d_
from enaml.widgets.raw_widget import RawWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
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


class JVResultsPanel(RawWidget):
    __slots__ = ('__weakref__',)

    is_dark_mode = d_(Bool(False))

    export_txt_requested = d_(Event(), writable=False)
    export_csv_requested = d_(Event(), writable=False)

    _table = Typed(QTableWidget)
    _export_txt_btn = Typed(QPushButton)
    _export_csv_btn = Typed(QPushButton)
    _shadow = Typed(object)
    _role_colored_items = List()  # [(QTableWidgetItem, role), ...] for theme refresh

    def create_widget(self, parent):
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.addWidget(self._build_results_panel())
        return container

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

        self._export_txt_btn = QPushButton("Export .TXT")
        self._export_txt_btn.clicked.connect(self._on_export_txt_clicked)
        self._export_txt_btn.setEnabled(False)
        header_row.addWidget(self._export_txt_btn)

        self._export_csv_btn = QPushButton("Export .CSV")
        self._export_csv_btn.clicked.connect(self._on_export_csv_clicked)
        self._export_csv_btn.setEnabled(False)
        header_row.addWidget(self._export_csv_btn)

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

        self._table = QTableWidget()
        self._table.setObjectName("ResultsTable")
        self._table.setFrameShape(QFrame.NoFrame)
        self._table.setColumnCount(len(_HEADERS))

        header = RichTextHeaderView(Qt.Horizontal, self._table)
        self._table.setHorizontalHeader(header)
        header.set_text_color(get_theme_colors(self.is_dark_mode)["accent"])

        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.setMinimumHeight(260)
        table_wrap_layout.addWidget(self._table)

        layout.addWidget(table_wrap)

        self._shadow = make_panel_shadow(panel, self.is_dark_mode)
        return panel

    def _on_export_txt_clicked(self):
        self.export_txt_requested = True

    def _on_export_csv_clicked(self):
        self.export_csv_requested = True

    # --- Public API for the controller ---

    def clear(self):
        self._table.setRowCount(0)
        self._role_colored_items = []

    def add_result_row(self, pixel, area, metrics, status, loop_idx=None):
        r = self._table.rowCount()
        self._table.insertRow(r)

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

        role_colored = list(self._role_colored_items)
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)

            if col > 0:
                item.setTextAlignment(Qt.AlignCenter)

            if col in _FIT_CELL_COLUMNS and value != "--":
                self._apply_role_color(item, "warning", role_colored)
                font = item.font()
                font.setItalic(True)
                font.setBold(True)
                item.setFont(font)

            if col == self._table.columnCount() - 1:
                # Status column: green for OK, red for any fault string
                self._apply_role_color(item, "success" if value == "OK" else "error", role_colored)
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self._table.setItem(r, col, item)
        self._role_colored_items = role_colored

    def _apply_role_color(self, item, role, role_colored):
        item.setForeground(QBrush(QColor(get_theme_colors(self.is_dark_mode)[role])))
        role_colored.append((item, role))

    def get_export_data(self):
        """Returns (headers, rows) as plain strings, with rich-text markup
        stripped, ready for a CSV writer. Keeps the raw QTableWidget out of
        the controller's hands."""
        headers = []
        for col in range(self._table.columnCount()):
            header_item = self._table.horizontalHeaderItem(col)
            raw = header_item.text() if header_item else ""
            headers.append(raw.replace("<sub>", "").replace("</sub>", ""))

        rows = []
        for r in range(self._table.rowCount()):
            rows.append([
                self._table.item(r, c).text() if self._table.item(r, c) else ""
                for c in range(self._table.columnCount())
            ])
        return headers, rows

    def has_rows(self):
        return self._table.rowCount() > 0

    def set_export_enabled(self, enabled):
        self._export_txt_btn.setEnabled(enabled)
        self._export_csv_btn.setEnabled(enabled)

    def apply_theme(self, colors, is_dark_mode):
        self.is_dark_mode = is_dark_mode
        update_shadow_color(self._shadow, is_dark_mode)

        for item, role in self._role_colored_items:
            item.setForeground(QBrush(QColor(colors[role])))

        header = self._table.horizontalHeader()
        if isinstance(header, RichTextHeaderView):
            header.set_text_color(colors["accent"])
