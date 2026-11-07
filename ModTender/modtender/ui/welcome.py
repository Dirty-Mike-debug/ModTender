"""First-run welcome tour: what ModTender found, and the four things worth knowing on day one."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget,
)

from . import theme
from .pages import button
from .widgets import icon


def _page(icon_name: str, title: str, text: str, extra: QWidget | None = None) -> QWidget:
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(8, 8, 8, 8)
    lay.setSpacing(14)
    mark = QLabel()
    mark.setPixmap(icon(icon_name, theme.ACCENT, 44).pixmap(44, 44))
    lay.addWidget(mark)
    head = QLabel(title, objectName="PageTitle", wordWrap=True)
    lay.addWidget(head)
    body = QLabel(text, wordWrap=True)
    body.setTextFormat(Qt.TextFormat.RichText)
    body.setObjectName("Muted")
    lay.addWidget(body)
    if extra is not None:
        lay.addWidget(extra)
    lay.addStretch()
    return page


class WelcomeTour(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Welcome to ModTender")
        self.setMinimumSize(QSize(600, 470))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 18)
        lay.setSpacing(14)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        games = [g for g in win.games]
        if games:
            names = ", ".join(g.name for g in games[:6]) + (f" and {len(games) - 6} more" if len(games) > 6 else "")
            found = (f"ModTender found <b>{len(games)} game{'s' if len(games) != 1 else ''}</b> with mods on this PC: "
                     f"{names}.")
        else:
            found = ("ModTender didn't find any modded games yet. You can add any game's mods folder in "
                     "<b>Settings → Games → Add game</b>.")
        self.backup = QCheckBox("Back up my mods now, so I can always get back to today's setup")
        self.backup.setChecked(bool(games))
        self.backup.setVisible(bool(games))
        self.pick = QComboBox()
        for g in games:
            self.pick.addItem(g.name, g.id)
        if win.game is not None:
            self.pick.setCurrentIndex(max(0, self.pick.findData(win.game.id)))
        self.pick.setVisible(len(games) > 1)
        start = QWidget()
        sl = QVBoxLayout(start)
        sl.setContentsMargins(0, 6, 0, 0)
        sl.setSpacing(10)
        if len(games) > 1:
            sl.addWidget(QLabel("Start with:", objectName="Muted"))
            sl.addWidget(self.pick)
        sl.addWidget(self.backup)

        pages = [
            _page("dashboard", "ModTender keeps your mods healthy",
                  f"{found}<br><br>It checks your mods for the problems that cause crashes and broken saves, explains "
                  "them in plain English, and fixes them for you. Nothing is ever deleted: anything ModTender "
                  "removes goes to a quarantine folder you can restore from."),
            _page("issues", "Scan, then fix",
                  "The <b>Dashboard</b> shows a health score for the game you pick. The <b>Issues</b> page lists "
                  "every problem with what to do about it.<br><br><b>Fix</b> sorts out one problem; <b>Fix all</b> "
                  "handles the safe ones together, and makes a backup first."),
            _page("crash", "When the game crashes",
                  "Press <b>Play</b> and ModTender checks your mods, starts the game, and watches for a crash. If "
                  "it crashes, ModTender names the mod most likely to blame.<br><br>No idea which mod it is? "
                  "<b>Find broken mod</b> turns mods off in halves while you test, until only the cause is left."),
            _page("shield", "Stay safe",
                  "<b>Backups</b> let you roll back to a setup that worked. Mark one as working and you can always "
                  "get back to it in one click.<br><br>New mods and updates are checked with your antivirus before "
                  "they're installed. Drag downloaded mods onto the window to install them in the right place."),
            _page("play", "You're all set", "Pick a game to start with. You can see this tour again any time from "
                  "<b>Settings → Updates</b>.", start),
        ]
        for p in pages:
            self.stack.addWidget(p)

        row = QHBoxLayout()
        self.skip = button("Skip tour", self.reject)
        row.addWidget(self.skip)
        row.addStretch()
        self.dots = QLabel(objectName="Muted")
        row.addWidget(self.dots)
        row.addStretch()
        self.back = button("Back", lambda: self._go(-1))
        self.next = button("Next", lambda: self._go(1), "Primary")
        row.addWidget(self.back)
        row.addWidget(self.next)
        lay.addLayout(row)
        self._go(0)

    def _go(self, step: int):
        i = self.stack.currentIndex() + step
        if i >= self.stack.count():
            self.accept()
            return
        self.stack.setCurrentIndex(max(0, i))
        i = self.stack.currentIndex()
        last = i == self.stack.count() - 1
        self.back.setVisible(i > 0)
        self.skip.setVisible(not last)
        self.next.setText("Get started" if last else "Next")
        self.dots.setText("  ".join("●" if n == i else "○" for n in range(self.stack.count())))

    @property
    def chosen_game(self) -> str:
        return self.pick.currentData() or ""

    @property
    def wants_backup(self) -> bool:
        return self.backup.isVisible() and self.backup.isChecked()
