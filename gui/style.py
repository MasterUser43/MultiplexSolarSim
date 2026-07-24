"""
Qt stylesheets (QSS) supporting Light and Dark modes.
"""

THEME_COLORS = {
    False: {  # Light mode
        "bg_base": "#f4f6f8",
        "bg_panel": "#ffffff",
        "bg_input": "#ffffff",
        "accent": "#0284c7",
        "accent_hover": "#0369a1",
        "accent_text_on": "#ffffff",
        "success": "#10b981",
        "error": "#ef4444",
        "warning": "#f59e0b",
        "text_main": "#1f2933",
        "text_dim": "#64748b",
        "border": "#cbd5e1",
        "row_hover": "rgba(0, 0, 0, 0.03)",
        "alt_row": "#eef2f6",
    },
    True: {  # Dark mode
        "bg_base": "#0b1120",
        "bg_panel": "#1e293b",
        "bg_input": "#0b1120",
        "accent": "#38bdf8",
        "accent_hover": "#0284c7",
        "accent_text_on": "#0b1120",
        "success": "#10b981",
        "error": "#ef4444",
        "warning": "#f59e0b",
        "text_main": "#f8fafc",
        "text_dim": "#94a3b8",
        "border": "#334155",
        "row_hover": "rgba(255, 255, 255, 0.03)",
        "alt_row": "#141c2e",
    },
}

def get_theme_colors(dark_mode=False):
    """Returns the color-token dict for the active theme."""
    return THEME_COLORS[bool(dark_mode)]


def _build_theme(c):
    """Builds the full QSS string from a color-token dict."""
    return f"""
    /* --- Base Structure --- */
    QWidget {{
        background-color: {c['bg_base']};
        color: {c['text_main']};
    }}

    QTabWidget::pane {{ border: none; }}

    QTabBar::tab {{
        padding: 12px 24px;
        font-weight: bold;
        letter-spacing: 1px;
        background: {c['bg_panel']};
        color: {c['text_dim']};
        border-bottom: 3px solid transparent;
    }}
    QTabBar::tab:hover {{
        color: {c['text_main']};
        background: {c['row_hover']};
    }}
    QTabBar::tab:selected {{
        color: {c['accent']};
        border-bottom: 3px solid {c['accent']};
        background: rgba(2, 132, 199, 0.08);
    }}

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {c['bg_input']};
        border: 1px solid {c['border']};
        color: {c['text_main']};
        border-radius: 6px;
        padding: 6px 10px;
        min-height: 24px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {c['accent']};
    }}

    QPushButton {{
        padding: 8px 16px;
        border-radius: 6px;
        font-weight: bold;
        border: 1px solid {c['border']};
        color: {c['text_main']};
        background-color: {c['bg_panel']};
    }}
    QPushButton:hover {{ background-color: {c['row_hover']}; }}

    QPushButton#PrimaryButton {{
        background-color: {c['accent']};
        color: {c['accent_text_on']};
        border: none;
    }}
    QPushButton#PrimaryButton:hover {{ background-color: {c['accent_hover']}; }}

    QPushButton#DangerButton {{
        background-color: {c['error']};
        color: white;
        border: none;
    }}
    QPushButton#DangerButton:hover {{ background-color: #dc2626; }}

    QPushButton#ThemeButton {{
        border-radius: 18px;
        padding: 0px;
        font-size: 14pt;
        min-height: 36px;
        max-height: 36px;
        min-width: 36px;
        max-width: 36px;
        background-color: {c['bg_input']};
        border: 1px solid {c['border']};
    }}
    QPushButton#ThemeButton:hover {{ background-color: {c['border']}; }}

    QProgressBar {{
        border-radius: 4px;
        text-align: center;
        color: transparent;
        max-height: 10px;
        background-color: {c['bg_input']};
        border: 1px solid {c['border']};
    }}
    QProgressBar::chunk {{
        border-radius: 4px;
        background-color: {c['accent']};
    }}

    QTableWidget {{
        border-radius: 6px;
        background-color: {c['bg_panel']};
        alternate-background-color: {c['alt_row']};
        border: 1px solid {c['border']};
        gridline-color: {c['border']};
    }}
    QHeaderView::section {{
        font-weight: bold;
        padding: 8px;
        border: none;
        background-color: {c['bg_input']};
        color: {c['accent']};
        border-bottom: 2px solid {c['border']};
    }}
    QTableView::item {{
        padding: 5px;
        border-bottom: 1px solid {c['border']};
    }}
    QTableView::item:selected {{
        background-color: {c['row_hover']};
        color: {c['text_main']};
    }}

    QTextEdit {{
        font-family: 'Consolas', monospace;
        border-radius: 6px;
        padding: 10px;
        background-color: {c['bg_input']};
        color: {c['text_main']};
        border: 1px solid {c['border']};
    }}
    // Transparency required for QLabels
    QLabel {{ background-color: transparent; border: none; }}

    /* --- Text Roles --- */
    QLabel#BrandTitle {{
        color: {c['accent']};
        font-weight: 850;
        font-size: 14pt;
        letter-spacing: 1px;
    }}
    QLabel#PanelTitle {{
        color: {c['accent']};
        font-weight: 800;
        font-size: 11px;
        letter-spacing: 1px;
    }}
    QLabel#AccentLabel {{
        color: {c['accent']};
        font-weight: 800;
        letter-spacing: 1px;
    }}
    QLabel#DimLabel {{
        color: {c['text_dim']};
        font-weight: 600;
    }}
    QLabel#MainLabel {{
        color: {c['text_main']};
        font-weight: bold;
    }}
    QLabel#HudActivePixel {{
        color: {c['accent']};
        font-weight: 800;
        font-size: 15px;
    }}

    /* Thin section divider, used under panel titles */
    QFrame#Divider {{
        border: none;
        border-bottom: 1px solid {c['border']};
    }}
    QFrame#VDivider {{
        border: none;
        border-left: 1px solid {c['border']};
    }}

    /* --- Status Indicators --- */
    QLabel#StatusLED {{
        border-radius: 6px;
        min-width: 12px;
        max-width: 12px;
        min-height: 12px;
        max-height: 12px;
    }}
    QLabel#StatusLED[status="idle"] {{ background-color: {c['text_dim']}; }}
    QLabel#StatusLED[status="ok"]   {{ background-color: {c['success']}; }}
    QLabel#StatusLED[status="bad"]  {{ background-color: {c['error']}; }}

    QLabel#StatusLabel {{
        font-weight: bold;
        font-size: 8.5pt;
        letter-spacing: 0.5px;
    }}
    QLabel#StatusLabel[status="idle"] {{ color: {c['text_dim']}; }}
    QLabel#StatusLabel[status="ok"]   {{ color: {c['text_main']}; }}
    QLabel#StatusLabel[status="bad"]  {{ color: {c['error']}; }}

    /* --- Flat Panel Containers --- */
    QFrame#PanelContainer {{
        border-radius: 10px;
        border: 1px solid {c['border']};
        background-color: {c['bg_panel']};
    }}

    /* Row Divider Lines inside forms */
    QFrame#FormRow {{
        border: none;
        background: transparent;
        border-bottom: 1px solid {c['row_hover']};
    }}
    QFrame#FormRow[last="true"] {{ border-bottom: none; }}

    /* --- Pixel Cards --- */
    QFrame#PixelCard {{
        border-radius: 6px;
        border: 1px solid {c['border']};
        background-color: {c['bg_input']};
        min-height: 38px;
        max-height: 38px;
    }}
    QFrame#PixelCard:hover {{ border-color: {c['accent']}; }}

    /* --- Metric Cards --- */
    QFrame#MetricCard {{
        border-radius: 8px;
        border: 1px solid {c['border']};
        background-color: {c['bg_input']};
    }}
    QLabel#MetricLabel {{
        color: {c['accent']};
        font-size: 11px;
        font-weight: bold;
        letter-spacing: 1px;
    }}
    QLabel#MetricValue {{
        color: {c['text_main']};
        font-size: 24px;
        font-weight: 800;
        letter-spacing: -0.5px;
    }}
    QLabel#MetricUnit {{
        color: {c['text_dim']};
        font-size: 13px;
        font-weight: 600;
    }}

    /* --- Progress Strip --- */
    QFrame#FooterStrip {{
        background-color: {c['bg_panel']};
        border: 1px solid {c['border']};
        border-radius: 8px;
    }}

    /* --- Rounded Checkbox :) --- */
    QCheckBox {{
        background: transparent;
        border: none;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {c['border']};
        background-color: {c['bg_input']};
    }}
    QCheckBox::indicator:checked {{
        background-color: {c['accent']};
        border-color: {c['accent']};
    }}

    /* --- Scrollbar Thinners --- */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['border']};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {c['accent']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c['border']};
        border-radius: 5px;
        min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {c['accent']}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
"""


DARK_THEME = _build_theme(THEME_COLORS[True])
LIGHT_THEME = _build_theme(THEME_COLORS[False])


def get_theme(dark_mode=False):
    return DARK_THEME if dark_mode else LIGHT_THEME
