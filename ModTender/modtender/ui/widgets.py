"""Reusable pieces: background tasks, icons, stat cards, the health gauge, sortable cells."""
from __future__ import annotations

import subprocess
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QThread, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout, QWidget

from . import theme

try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:  # icons are optional
    QSvgRenderer = None


class Task(QThread):
    """Run fn(*args, progress=callback) off the UI thread so the window never freezes."""

    progress = Signal(int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self.fn, self.args = fn, args

    def run(self):
        try:
            result = self.fn(*self.args, progress=lambda p, msg: self.progress.emit(int(p), str(msg)))
            self.done.emit(result)
        except Exception as exc:  # report to the UI instead of crashing
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")


# ---------------------------------------------------------------- icons (Lucide-style line icons)

_PATHS = {
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/>'
                 '<rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    "mods": '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5"/><path d="M12 13v8"/>',
    "issues": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
              '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "backups": '<rect x="2" y="3" width="20" height="5" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/>'
               '<path d="M10 12h4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1'
                'a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3'
                'l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1'
                ' 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1'
                'a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21'
                'a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "scan": '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    "update": '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "crash": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "report": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>'
              '<path d="M8 13h8"/><path d="M8 17h5"/>',
    "save": '<path d="M12 3v10"/><path d="m8 9 4 4 4-4"/><rect x="3" y="15" width="18" height="6" rx="1"/>',
    "fix": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3'
           'l6.9-6.9a6 6 0 0 1 7.9-7.9z"/>',
    "sources": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18"/>'
               '<path d="M12 3a14 14 0 0 0 0 18"/>',
    "external": '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "palette": '<circle cx="13.5" cy="6.5" r="1"/><circle cx="17.5" cy="10.5" r="1"/><circle cx="8.5" cy="7.5" r="1"/>'
               '<circle cx="6.5" cy="12.5" r="1"/><path d="M12 2a10 10 0 0 0 0 20c1 0 1.7-.8 1.7-1.7 0-.4-.2-.8-.4-1.1'
               '-.3-.3-.4-.7-.4-1.1 0-.9.8-1.7 1.7-1.7h2a5.6 5.6 0 0 0 5.4-5.6C22 6 17.5 2 12 2z"/>',
}

# Cog with an M: the ModTender mark. {accent} follows the theme; the tile stays dark.
GEAR_PATH = "M26.25 11.28L27.22 4.92L36.78 4.92L37.75 11.28A21.5 21.5 0 0 1 42.59 13.29L47.77 9.47L54.53 16.23L50.71 21.41A21.5 21.5 0 0 1 52.72 26.25L59.08 27.22L59.08 36.78L52.72 37.75A21.5 21.5 0 0 1 50.71 42.59L54.53 47.77L47.77 54.53L42.59 50.71A21.5 21.5 0 0 1 37.75 52.72L36.78 59.08L27.22 59.08L26.25 52.72A21.5 21.5 0 0 1 21.41 50.71L16.23 54.53L9.47 47.77L13.29 42.59A21.5 21.5 0 0 1 11.28 37.75L4.92 36.78L4.92 27.22L11.28 26.25A21.5 21.5 0 0 1 13.29 21.41L9.47 16.23L16.23 9.47L21.41 13.29A21.5 21.5 0 0 1 26.25 11.28Z"
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="14" fill="#10161d"/>'
    '<path d="' + GEAR_PATH + '" fill="{accent}"/>'
    '<circle cx="32" cy="32" r="14.5" fill="#10161d"/>'
    '<path d="M24.5 39.5V24.5L32 32.5L39.5 24.5V39.5" fill="none" stroke="#ffffff" stroke-width="3.6" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
ASSETS = Path(__file__).resolve().parents[1] / "assets"


def _render(svg: str, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    if QSvgRenderer is not None:
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        painter = QPainter(pm)
        renderer.render(painter)
        painter.end()
    return pm


def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    path = _PATHS.get(name)
    if not path or QSvgRenderer is None:
        return QIcon()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color or theme.TEXT}" '
           f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{path}</svg>')
    return QIcon(_render(svg, size * 2))  # 2x for sharp rendering on high-DPI screens


def logo_pixmap(size: int = 32) -> QPixmap:
    return _render(LOGO_SVG.replace("{accent}", theme.ACCENT), size)


def app_icon() -> QIcon:
    """The fixed brand icon for the window and taskbar (same as the .exe icon)."""
    ico = ASSETS / "modtender.ico"
    return QIcon(str(ico)) if ico.exists() else QIcon(logo_pixmap(64))


# ---------------------------------------------------------------- cards

class StatCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(128)
        self.setMaximumHeight(170)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(4)
        self.title = QLabel(title.upper(), objectName="CardTitle")
        self.value = QLabel("–", objectName="CardValue")
        self.sub = QLabel("", objectName="CardSub")
        self.sub.setWordWrap(True)
        lay.addWidget(self.title)
        lay.addStretch()
        lay.addWidget(self.value)
        lay.addWidget(self.sub)

    def set(self, value: str, sub: str = "", color: str | None = None):
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color};" if color else "")
        self.sub.setText(sub)


class HealthRing(QWidget):
    """Circular gauge showing the 0-100 health score."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.score: int | None = None
        self.setFixedSize(84, 84)

    def set_score(self, score: int | None):
        self.score = score
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(6, 6, self.width() - 12, self.height() - 12)
        track = QPen(QColor(theme.BORDER), 7)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(track)
        p.drawArc(rect, 0, 360 * 16)
        if self.score is not None:
            arc = QPen(QColor(theme.score_color(self.score)), 7)
            arc.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(arc)
            p.drawArc(rect, 90 * 16, int(-360 * 16 * self.score / 100))
        p.setPen(QColor(theme.TEXT))
        font = p.font()
        font.setPointSizeF(15)
        font.setWeight(font.Weight.DemiBold)
        p.setFont(font)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "–" if self.score is None else str(self.score))
        p.end()


class HealthCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(128)
        self.setMaximumHeight(170)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(16)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(QLabel("HEALTH", objectName="CardTitle"))
        col.addStretch()
        self.label = QLabel("–", objectName="CardValue")
        self.label.setStyleSheet("font-size: 14pt;")
        self.sub = QLabel("", objectName="CardSub")
        self.sub.setWordWrap(True)
        col.addWidget(self.label)
        col.addWidget(self.sub)
        lay.addLayout(col, 1)
        self.ring = HealthRing()
        lay.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignVCenter)

    def set(self, score: int | None, label: str, sub: str = ""):
        self.ring.set_score(score)
        color = theme.score_color(score) if score is not None else None
        self.label.setText(label)
        self.label.setStyleSheet(f"font-size: 14pt; color: {color};" if color else "font-size: 14pt;")
        self.sub.setText(sub)


def divider() -> QFrame:
    line = QFrame(objectName="Divider")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


class SortItem(QTableWidgetItem):
    """Table cell that shows text but sorts by a hidden value (e.g. bytes, timestamps)."""

    def __init__(self, text: str, sort_value=None):
        super().__init__(text)
        self.sort_value = text.lower() if sort_value is None else sort_value
        self.setFlags(self.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def __lt__(self, other):
        if isinstance(other, SortItem):
            try:
                return self.sort_value < other.sort_value
            except TypeError:
                return str(self.sort_value) < str(other.sort_value)
        return super().__lt__(other)


def reveal_in_explorer(path: Path):
    """Open Explorer with the file selected (or just open the folder)."""
    path = Path(path)
    if sys.platform == "win32" and path.exists():
        if path.is_file():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            subprocess.Popen(["explorer", str(path)])
        return
    target = path if path.is_dir() else path.parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
