"""Small reusable pieces: background tasks, stat cards, sortable table items."""
from __future__ import annotations

import subprocess
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QLabel, QTableWidgetItem, QVBoxLayout


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


class StatCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(118)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        self.title = QLabel(title.upper(), objectName="CardTitle")
        self.value = QLabel("-", objectName="CardValue")
        self.sub = QLabel("", objectName="CardSub")
        self.sub.setWordWrap(True)
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addWidget(self.sub)
        lay.addStretch()

    def set(self, value: str, sub: str = "", color: str | None = None):
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color};" if color else "")
        self.sub.setText(sub)


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
