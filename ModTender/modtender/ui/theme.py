"""ModTender's dark theme."""

BG = "#0f1419"
PANEL = "#161d24"
CARD = "#1c252e"
BORDER = "#2a3540"
TEXT = "#e6edf3"
MUTED = "#8b98a5"
ACCENT = "#3ecf8e"
ACCENT_DARK = "#2ea875"
CRITICAL = "#f26d6d"
WARNING = "#f2b84b"
INFO = "#5aa9f2"

SEVERITY_COLORS = {"critical": CRITICAL, "warning": WARNING, "info": INFO}


def score_color(score: int) -> str:
    if score >= 90:
        return ACCENT
    if score >= 70:
        return WARNING
    return CRITICAL


STYLESHEET = f"""
* {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QWidget#Page {{ background: {BG}; }}
QWidget#Sidebar {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
QLabel#Logo {{ font-size: 18pt; font-weight: 700; color: {ACCENT}; }}
QLabel#LogoSub {{ color: {MUTED}; font-size: 9pt; }}
QLabel#PageTitle {{ font-size: 18pt; font-weight: 600; }}
QLabel#Muted, QLabel#SectionHint {{ color: {MUTED}; }}
QLabel#Section {{ font-size: 11pt; font-weight: 600; margin-top: 6px; }}

QPushButton#Nav {{
    text-align: left; padding: 9px 14px; border: none; border-radius: 8px;
    background: transparent; color: {MUTED}; font-size: 10.5pt;
}}
QPushButton#Nav:hover {{ background: {CARD}; color: {TEXT}; }}
QPushButton#Nav:checked {{ background: {CARD}; color: {ACCENT}; font-weight: 600; }}

QPushButton {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 7px; padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; border-color: {BORDER}; }}
QPushButton#Primary {{ background: {ACCENT}; color: #06210f; border: none; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {ACCENT_DARK}; }}
QPushButton#Danger:hover {{ border-color: {CRITICAL}; color: {CRITICAL}; }}

QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#CardTitle {{ color: {MUTED}; font-size: 9pt; }}
QLabel#CardValue {{ font-size: 22pt; font-weight: 700; }}
QLabel#CardSub {{ color: {MUTED}; font-size: 9pt; }}

QComboBox, QLineEdit, QSpinBox {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 7px; padding: 6px 8px;
}}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {BORDER}; selection-background-color: {BORDER}; }}

QTableWidget, QListWidget, QTextBrowser {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px;
    gridline-color: transparent; selection-background-color: #24404a; alternate-background-color: #19212a;
}}
QTableWidget::item, QListWidget::item {{ padding: 5px; }}
QHeaderView::section {{
    background: {PANEL}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 7px; font-weight: 600;
}}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QCheckBox::indicator {{ width: 16px; height: 16px; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QProgressBar {{ background: {CARD}; border: none; border-radius: 4px; max-height: 8px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; }}
"""
