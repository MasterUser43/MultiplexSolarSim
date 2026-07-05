"""
Isolated Qt stylesheet (QSS) for the main window.
"""

STYLE_SHEET = """
            QWidget#Root {
                background: #f4f6f8;
                color: #1f2933;
            }
            QFrame#Header {
                background: #14213d;
                border: 0;
            }
            QLabel#Title {
                color: #ffffff;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#Subtitle {
                color: #c9d6e2;
                font-size: 11px;
                letter-spacing: 0px;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d9e2ec;
                border-radius: 6px;
                margin-top: 0px;
                padding: 18px 10px 10px 10px;
                font-weight: 700;
            }
            QGroupBox::title {
                subcontrol-origin: border;
                subcontrol-position: top left;
                top: 2px;
                left: 12px;
                padding: 0 3px;
                color: #243b53;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
                background: #ffffff;
                border: 1px solid #bcccdc;
                border-radius: 4px;
                padding: 5px 7px;
                selection-background-color: #3d5a80;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                min-height: 32px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border: 1px solid #2f80ed;
            }
            QPushButton {
                background: #e9eef4;
                border: 1px solid #c7d2df;
                border-radius: 4px;
                padding: 9px 14px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #dde7f2;
            }
            QPushButton:pressed {
                background: #c8d7e6;
            }
            QPushButton#PrimaryButton {
                background: #1b5e8c;
                border-color: #15486b;
                color: #ffffff;
            }
            QPushButton#PrimaryButton:hover {
                background: #236fa4;
            }
            QPushButton#DangerButton {
                background: #b42318;
                border-color: #8f1d15;
                color: #ffffff;
            }
            QPushButton#DangerButton:hover {
                background: #c9372c;
            }
            QLabel[status="ok"] {
                background: #e3f8ec;
                color: #17633a;
                border: 1px solid #a8e6bf;
                border-radius: 4px;
                padding: 5px 8px;
                font-weight: 700;
            }
            QLabel[status="bad"] {
                background: #fdecea;
                color: #9b1c1c;
                border: 1px solid #f4b4ad;
                border-radius: 4px;
                padding: 5px 8px;
                font-weight: 700;
            }
            QLabel[status="idle"] {
                background: #edf2f7;
                color: #4a5568;
                border: 1px solid #cbd5e0;
                border-radius: 4px;
                padding: 5px 8px;
                font-weight: 700;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d9e2ec;
                gridline-color: #e6ecf2;
                alternate-background-color: #f8fafc;
            }
            QHeaderView::section {
                background: #243b53;
                color: #ffffff;
                border: 0;
                padding: 7px;
                font-weight: 700;
            }
            QTextEdit {
                font-family: Consolas, "Courier New", monospace;
                font-size: 9pt;
                background: #0f172a;
                color: #dbeafe;
                border: 1px solid #1e293b;
            }
"""
