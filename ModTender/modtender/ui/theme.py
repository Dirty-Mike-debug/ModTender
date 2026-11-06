"""Themes: built-in presets plus user overrides. apply() rebuilds the stylesheet live.

Pages read colors from this module's globals (theme.ACCENT, theme.MUTED, ...) at refresh time,
so changing the theme only requires apply() followed by a refresh of the pages."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Palette:
    bg: str
    sidebar: str
    surface: str
    border: str
    text: str
    muted: str
    accent: str
    critical: str = "#f0605d"
    warning: str = "#e5a93b"
    info: str = "#4f9cf0"
    success: str = "#3ecf8e"  # "healthy / enabled" stays green whatever the accent is
    dark: bool = True


PRESETS: dict[str, Palette] = {
    "Midnight": Palette("#0d1117", "#10151c", "#161b22", "#262d36", "#e6edf3", "#8b949e", "#3ecf8e"),
    "Graphite": Palette("#141414", "#191919", "#1f1f1f", "#2e2e2e", "#ececec", "#9b9b9b", "#4f8cff"),
    "Nord": Palette("#2e3440", "#2a2f3a", "#3b4252", "#4c566a", "#eceff4", "#a7b0c0", "#88c0d0",
                    critical="#bf616a", warning="#ebcb8b", info="#81a1c1"),
    "Daylight": Palette("#f4f6f9", "#ffffff", "#ffffff", "#dde3ea", "#1b2430", "#5f6b7a", "#2563eb",
                        critical="#d33a3a", warning="#b7791f", info="#2563eb", success="#16a34a", dark=False),
}

ACCENT_SWATCHES = ["#3ecf8e", "#2dd4bf", "#4f8cff", "#a371f7", "#ec6cb9", "#f85149", "#f0883e", "#e3b341"]

# User-editable colors shown in Settings, in display order.
EDITABLE = [("accent", "Accent"), ("bg", "Background"), ("sidebar", "Sidebar"),
            ("surface", "Cards & tables"), ("border", "Borders"), ("text", "Text"), ("muted", "Secondary text")]

# Live values (updated by apply)
BG = SIDEBAR = SURFACE = BORDER = TEXT = MUTED = ACCENT = CRITICAL = WARNING = INFO = SUCCESS = ""
SEVERITY_COLORS: dict[str, str] = {}
CURRENT: Palette = PRESETS["Midnight"]
COMPACT = False  # tighter rows and margins
TEXT_SCALES = {"Small": 0.9, "Normal": 1.0, "Large": 1.15, "Extra large": 1.3}


def _mix(a: str, b: str, t: float) -> str:
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
    ).name()


def _on_color(color: str) -> str:
    """Black or white text, whichever reads better on `color`."""
    c = QColor(color)
    luminance = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return "#0b1410" if luminance > 150 else "#ffffff"


def resolve(preset: str, overrides: dict | None) -> Palette:
    base = PRESETS.get(preset, PRESETS["Midnight"])
    valid = {k: v for k, v in (overrides or {}).items()
             if k in asdict(base) and k not in ("dark", "success") and QColor(v).isValid()}
    pal = replace(base, **valid)
    # A custom background decides light vs dark mode.
    return replace(pal, dark=QColor(pal.bg).lightness() < 128)


def score_color(score: int) -> str:
    return SUCCESS if score >= 90 else WARNING if score >= 70 else CRITICAL


def apply(app, preset: str = "Midnight", overrides: dict | None = None, scale: float = 1.0,
          compact: bool = False) -> Palette:
    global BG, SIDEBAR, SURFACE, BORDER, TEXT, MUTED, ACCENT, CRITICAL, WARNING, INFO, SUCCESS, CURRENT, COMPACT
    COMPACT = compact
    p = resolve(preset, overrides)
    CURRENT = p
    BG, SIDEBAR, SURFACE, BORDER, TEXT, MUTED = p.bg, p.sidebar, p.surface, p.border, p.text, p.muted
    ACCENT, CRITICAL, WARNING, INFO, SUCCESS = p.accent, p.critical, p.warning, p.info, p.success
    SEVERITY_COLORS.clear()
    SEVERITY_COLORS.update(critical=CRITICAL, warning=WARNING, info=INFO)
    if app is not None:
        css = stylesheet(p)
        if scale and abs(scale - 1.0) > 0.01:
            import re
            css = re.sub(r"(\d+(?:\.\d+)?)pt", lambda m: f"{float(m.group(1)) * scale:.1f}pt", css)
        if compact:
            css = css.replace("padding: 6px 14px", "padding: 4px 10px").replace("padding: 8px 12px", "padding: 5px 10px")
        app.setStyleSheet(css)
    return p


def stylesheet(p: Palette) -> str:
    hover = _mix(p.surface, p.text, 0.06)
    pressed = _mix(p.surface, p.text, 0.10)
    selection = _mix(p.surface, p.accent, 0.22)
    alt_row = _mix(p.surface, p.text, 0.025)
    nav_active = _mix(p.sidebar, p.accent, 0.14)
    accent_hover = _mix(p.accent, "#ffffff" if p.dark else "#000000", 0.12)
    on_accent = _on_color(p.accent)
    input_bg = _mix(p.bg, p.surface, 0.5)
    return f"""
* {{ font-family: "Segoe UI"; font-size: 9.5pt; color: {p.text}; }}
QMainWindow, QDialog {{ background: {p.bg}; }}
QWidget#Page {{ background: {p.bg}; }}
QWidget#Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}

QLabel#Brand {{ font-size: 13pt; font-weight: 700; }}
QLabel#BrandSub {{ color: {p.muted}; font-size: 8.5pt; }}
QLabel#SideLabel {{ color: {p.muted}; font-size: 8pt; font-weight: 600; padding-left: 2px; }}
QLabel#PageTitle {{ font-size: 15pt; font-weight: 600; }}
QLabel#Muted {{ color: {p.muted}; }}
QLabel#Section {{ font-size: 10.5pt; font-weight: 600; }}
QLabel#Version {{ color: {p.muted}; font-size: 8.5pt; }}

QPushButton#Nav {{
    text-align: left; padding: 8px 12px; border: none; border-radius: 6px;
    background: transparent; color: {p.muted}; font-size: 9.5pt; font-weight: 500;
}}
QPushButton#Nav:hover {{ background: {hover}; color: {p.text}; }}
QPushButton#Nav:checked {{ background: {nav_active}; color: {p.text}; font-weight: 600; }}

QPushButton {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 6px;
    padding: 6px 14px; min-height: 18px; font-weight: 500;
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {pressed}; }}
QPushButton:disabled {{ color: {p.muted}; }}
QPushButton#Primary {{ background: {p.accent}; color: {on_accent}; border: 1px solid {p.accent}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#Primary:disabled {{ background: {p.border}; border-color: {p.border}; color: {p.muted}; }}
QPushButton#Star {{ padding: 0; min-height: 0; font-size: 12pt; }}
QPushButton#Danger {{ color: {p.critical}; }}
QPushButton#Danger:hover {{ border-color: {p.critical}; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {p.muted}; text-align: left; padding: 6px 10px; }}
QPushButton#Ghost:hover {{ color: {p.text}; background: {hover}; }}
QPushButton#Swatch {{ border-radius: 12px; min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; padding: 0; }}

QFrame#Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; }}
QLabel#CardTitle {{ color: {p.muted}; font-size: 8.5pt; font-weight: 600; }}
QLabel#CardValue {{ font-size: 20pt; font-weight: 600; }}
QLabel#CardSub {{ color: {p.muted}; font-size: 8.5pt; }}
QFrame#Divider {{ background: {p.border}; max-height: 1px; min-height: 1px; border: none; }}

QComboBox, QLineEdit, QSpinBox {{
    background: {input_bg}; border: 1px solid {p.border}; border-radius: 6px; padding: 5px 9px; min-height: 18px;
}}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover {{ border-color: {_mix(p.border, p.text, 0.25)}; }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{ border-color: {p.accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {p.surface}; border: 1px solid {p.border}; outline: none; padding: 4px;
    selection-background-color: {selection}; selection-color: {p.text};
}}

QTableWidget, QListWidget, QTextBrowser {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; outline: none;
    gridline-color: transparent; selection-background-color: {selection}; selection-color: {p.text};
    alternate-background-color: {alt_row};
}}
QTableWidget::item {{ padding: 0 10px; border: none; }}
QListWidget::item {{ padding: 8px 10px; border-bottom: 1px solid {_mix(p.surface, p.border, 0.6)}; }}
QHeaderView::section {{
    background: {p.surface}; color: {p.muted}; border: none; border-bottom: 1px solid {p.border};
    padding: 8px 10px; font-size: 8.5pt; font-weight: 600;
}}
QHeaderView {{ background: transparent; border-top-left-radius: 10px; border-top-right-radius: 10px; }}
QTableCornerButton::section {{ background: {p.surface}; border: none; }}
QScrollArea, QScrollArea > QWidget > QWidget#ScrollBody {{ background: transparent; border: none; }}
QSplitter::handle {{ background: transparent; height: 10px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
QScrollBar::handle {{ background: {_mix(p.surface, p.text, 0.18)}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {_mix(p.surface, p.text, 0.30)}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; width: 0; background: none; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {p.border}; border-radius: 4px; background: {input_bg}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}

QStatusBar {{ background: {p.sidebar}; color: {p.muted}; border-top: 1px solid {p.border}; font-size: 8.5pt; }}
QStatusBar::item {{ border: none; }}
QProgressBar {{ background: {p.border}; border: none; border-radius: 3px; max-height: 6px; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}
QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; padding: 6px 8px; border-radius: 4px; }}
QMessageBox, QInputDialog {{ background: {p.bg}; }}
"""


apply(None)
