"""
Qt stylesheets (QSS) for the main window, supporting Light and Dark modes.
"""

_BASE_STYLE = """
    QTabWidget::pane { 
        border: none; 
    }

    QTabBar::tab { 
        padding: 12px 24px; 
        font-weight: bold; 
        letter-spacing: 1px; 
    }

    QGroupBox { 
        border-radius: 8px; 
        margin-top: 1.5ex; 
        padding: 15px; 
    }

    QGroupBox::title { 
        subcontrol-origin: margin; 
        subcontrol-position: top left; 
        left: 15px; 
        font-weight: bold; 
        text-transform: uppercase; 
        letter-spacing: 1px; 
    }

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { 
        border-radius: 4px; 
        padding: 6px 10px; 
        min-height: 24px; 
    }

    QPushButton { 
        padding: 8px 16px; 
        border-radius: 4px; 
        font-weight: bold; 
        border: 1px solid transparent; 
    }

    QProgressBar { 
        border-radius: 4px; 
        text-align: center; 
        color: transparent; 
        max-height: 10px; 
    }

    QProgressBar::chunk { 
        border-radius: 4px; 
    }

    QTableWidget { 
        border-radius: 6px; 
    }

    QHeaderView::section { 
        font-weight: bold; 
        padding: 8px; 
        border: none; 
    }

    QTableView::item { 
        padding: 5px; 
    }

    QTextEdit { 
        font-family: 'Consolas', monospace; 
        border-radius: 6px; 
        padding: 10px; 
    }

    /* Static Layout Rules for circular indicators */
    QLabel#StatusLED {
        border-radius: 6px;
        min-width: 12px;
        max-width: 12px;
        min-height: 12px;
        max-height: 12px;
    }

    QLabel#StatusLabel {
        font-weight: bold;
        font-size: 8.5pt;
        letter-spacing: 0.5px;
    }

    QPushButton#ThemeButton {
        border-radius: 18px; 
        padding: 0px;       
        font-size: 14pt;
        min-height: 36px;
        max-height: 36px;
        min-width: 36px;
        max-width: 36px;
    }
"""

DARK_THEME = _BASE_STYLE + """
    QWidget { 
        background-color: #0b1120; 
        color: #f8fafc; 
    }

    /* Tab Bar */
    QTabBar::tab { 
        background: #1e293b; 
        color: #94a3b8; 
        border-bottom: 3px solid transparent; 
    }
    QTabBar::tab:hover { 
        color: #f8fafc; 
        background: #253347; 
    }
    QTabBar::tab:selected { 
        color: #38bdf8; 
        border-bottom: 3px solid #38bdf8; 
        background: rgba(56, 189, 248, 0.08); 
    }

    /* Hardware LEDs & Labels (Dark Colors) */
    QLabel#StatusLED[status="idle"]  { background-color: #475569; }
    QLabel#StatusLED[status="ok"]    { background-color: #10b981; }
    QLabel#StatusLED[status="bad"]   { background-color: #ef4444; }

    QLabel#StatusLabel[status="idle"] { color: #64748b; }
    QLabel#StatusLabel[status="ok"]   { color: #f8fafc; }
    QLabel#StatusLabel[status="bad"]  { color: #f87171; }

    /* Group Boxes */
    QGroupBox { 
        background-color: #1e293b; 
        border: 1px solid #334155; 
    }
    QGroupBox::title { 
        color: #38bdf8; 
    }

    /* Inputs */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { 
        background-color: #0b1120; 
        border: 1px solid #334155; 
        color: #f8fafc; 
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { 
        border: 1px solid #38bdf8; 
    }

    /* Buttons */
    QPushButton { 
        color: #f8fafc; 
        border-color: #334155; 
        background-color: transparent; 
    }
    QPushButton:hover { 
        background-color: rgba(255, 255, 255, 0.05); 
    }
    
    QPushButton#PrimaryButton { 
        background-color: #38bdf8; 
        color: #0b1120; 
        border: none; 
    }
    QPushButton#PrimaryButton:hover { 
        background-color: #0284c7; 
    }
    
    QPushButton#DangerButton { 
        background-color: #ef4444; 
        color: white; 
        border: none; 
    }
    QPushButton#DangerButton:hover { 
        background-color: #dc2626; 
    }
    
    QPushButton#ThemeButton { 
        background-color: #1e293b; 
        border: 1px solid #334155; 
    }
    QPushButton#ThemeButton:hover { 
        background-color: #334155; 
    }

    /* Progress & Tables */
    QProgressBar { 
        background-color: #0b1120; 
    }
    QProgressBar::chunk { 
        background-color: #38bdf8; 
    }
    
    QTableWidget { 
        background-color: #0b1120; 
        border: 1px solid #334155; 
        gridline-color: #1e293b; 
    }
    QHeaderView::section { 
        background-color: #1e293b; 
        color: #38bdf8; 
        border-bottom: 2px solid #334155; 
    }
    QTableView::item { 
        border-bottom: 1px solid #1e293b; 
    }
    
    QTextEdit { 
        background-color: #0b1120; 
        color: #cbd5e1; 
        border: 1px solid #334155; 
    }
"""

LIGHT_THEME = _BASE_STYLE + """
    QWidget { 
        background-color: #f4f6f8; 
        color: #1f2933; 
    }

    /* Tab Bar */
    QTabBar::tab { 
        background: #e2e8f0; 
        color: #64748b; 
        border-bottom: 3px solid transparent; 
    }
    QTabBar::tab:hover { 
        color: #1f2933; 
        background: #cbd5e1; 
    }
    QTabBar::tab:selected { 
        color: #0284c7; 
        border-bottom: 3px solid #0284c7; 
        background: #ffffff; 
    }

    /* Hardware LEDs & Labels (Light Colors) */
    QLabel#StatusLED[status="idle"]  { background-color: #94a3b8; }
    QLabel#StatusLED[status="ok"]    { background-color: #10b981; }
    QLabel#StatusLED[status="bad"]   { background-color: #ef4444; }

    QLabel#StatusLabel[status="idle"] { color: #64748b; }
    QLabel#StatusLabel[status="ok"]   { color: #1f2933; }
    QLabel#StatusLabel[status="bad"]  { color: #b91c1c; }

    /* Group Boxes */
    QGroupBox { 
        background-color: #ffffff; 
        border: 1px solid #cbd5e1; 
    }
    QGroupBox::title { 
        color: #0284c7; 
    }

    /* Inputs */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { 
        background-color: #ffffff; 
        border: 1px solid #cbd5e1; 
        color: #1f2933; 
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { 
        border: 1px solid #0284c7; 
    }

    /* Buttons */
    QPushButton { 
        color: #1f2933; 
        border-color: #cbd5e1; 
        background-color: #ffffff; 
    }
    QPushButton:hover { 
        background-color: #f1f5f9; 
    }
    
    QPushButton#PrimaryButton { 
        background-color: #0284c7; 
        color: #ffffff; 
        border: none; 
    }
    QPushButton#PrimaryButton:hover { 
        background-color: #0369a1; 
    }
    
    QPushButton#DangerButton { 
        background-color: #dc2626; 
        color: white; 
        border: none; 
    }
    QPushButton#DangerButton:hover { 
        background-color: #b91c1c; 
    }
    
    QPushButton#ThemeButton { 
        background-color: #ffffff; 
        border: 1px solid #cbd5e1; 
    }
    QPushButton#ThemeButton:hover { 
        background-color: #f1f5f9; 
    }

    /* Progress & Tables */
    QProgressBar { 
        background-color: #e2e8f0; 
        border: 1px solid #cbd5e1; 
    }
    QProgressBar::chunk { 
        background-color: #0284c7; 
    }
    
    QTableWidget { 
        background-color: #ffffff; 
        border: 1px solid #cbd5e1; 
        gridline-color: #e2e8f0; 
    }
    QHeaderView::section { 
        background-color: #f1f5f9; 
        color: #0284c7; 
        border-bottom: 2px solid #cbd5e1; 
    }
    QTableView::item { 
        border-bottom: 1px solid #e2e8f0; 
    }
    
    QTextEdit { 
        background-color: #f8fafc; 
        color: #334155; 
        border: 1px solid #cbd5e1; 
    }
"""

def get_theme(dark_mode=False):
    return DARK_THEME if dark_mode else LIGHT_THEME