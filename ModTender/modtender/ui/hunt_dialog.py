"""The "Find the broken mod" window: one round at a time, while the player tests the game."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout

from ..core import bisect
from .pages import button

# Games where turning mods off by moving files would lose the player's load order or mod list.
UNSUPPORTED = {
    "skyrimse": "Skyrim keeps its load order in plugins.txt, which this would scramble",
    "fallout4": "Fallout 4 keeps its load order in plugins.txt, which this would scramble",
    "bg3": "Baldur's Gate 3 would drop the missing mods from its mod list",
    "rimworld": "RimWorld would drop the missing mods from its active mod list",
    "ets2": "the game would drop the missing mods from your profile",
    "ats": "the game would drop the missing mods from your profile",
    "arma3": "Arma 3 loads the mods you tick in the Arma 3 Launcher, not whatever is in its folder",
    "dayz": "DayZ loads the mods you pick in the DayZ Launcher, not whatever is in its folder",
    "warhammer3": "Total War's launcher keeps its own list of ticked mods, which this would scramble",
    "reforger": "Arma Reforger manages its mods in its own Workshop menu and would download missing ones again",
}


def unsupported_reason(game) -> str:
    if getattr(game, "workshop_only", False):
        return "Steam Workshop mods can only be turned off in Steam."
    why = UNSUPPORTED.get(game.definition.id)
    return (f"This isn't available for {game.name} yet: {why}. Use the game's own launcher or mod manager "
            "to turn mods off in halves instead.") if why else ""


class HuntDialog(QDialog):
    def __init__(self, win, game, hunt):
        super().__init__(win)
        self.win, self.game, self.hunt = win, game, hunt
        self.setWindowTitle("Find the broken mod")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        self.head = QLabel(objectName="Section")
        self.body = QLabel(wordWrap=True)
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        self.list_label = QLabel(objectName="Muted")
        self.list = QPlainTextEdit(readOnly=True)
        self.list.setMaximumHeight(150)
        self.tip = QLabel(wordWrap=True, objectName="Muted")
        for w in (self.head, self.body, self.list_label, self.list, self.tip):
            lay.addWidget(w)
        self.buttons = QHBoxLayout()
        lay.addLayout(self.buttons)
        self.render()

    # ------------------------------------------------------------ drawing

    def _clear_buttons(self):
        while self.buttons.count():
            w = self.buttons.takeAt(0).widget()
            if w:
                w.deleteLater()

    def render(self):
        self._clear_buttons()
        h = self.hunt
        n_off = len(h.testing_off)
        self.tip.setText("Don't save your game during the search: some games forget mods that were missing "
                         "when you saved. Leave ModTender open, or reopen it later to carry on.")
        if h.phase == "found":
            culprit = h.suspects[0]
            self.head.setText(f"Found it: {h.name(culprit)}")
            self.body.setText(f"The problem goes away when {h.name(culprit)} is off, and it was the only mod "
                              f"left that could cause it.\n\nUpdate or replace it (check its mod page for a fix), "
                              "or leave it off. File: " + culprit)
            self._show_list("", [])
            self.tip.setText("")
            self.buttons.addStretch()
            self.buttons.addWidget(button("Turn everything back on", lambda: self._finish([])))
            self.buttons.addWidget(button(f"Keep it off, turn the rest back on",
                                          lambda: self._finish([culprit]), "Primary", "fix"))
            return
        if h.phase in ("not_mods", "stuck"):
            if h.phase == "not_mods":
                self.head.setText("It's probably not a mod")
                self.body.setText("The problem happened even with every mod turned off, so a mod most likely "
                                  "isn't the cause. Try verifying the game's files (Steam: right-click the "
                                  "game, Properties, Installed Files, Verify) or updating your graphics driver.")
                self._show_list("", [])
            else:
                self.head.setText("Couldn't narrow it down to one mod")
                self.body.setText("This happens when two mods only break when they're both on, or when the "
                                  "problem doesn't happen every time. These mods were still suspects:")
                self._show_list("Still suspects:", h.suspects)
            self.tip.setText("")
            self.buttons.addStretch()
            self.buttons.addWidget(button("Turn everything back on", lambda: self._finish([]), "Primary"))
            return

        total = max(h.total_rounds, h.round)
        if h.phase == "mods_at_all":
            self.head.setText(f"Round 1 of about {total}: is it a mod at all?")
            self.body.setText(f"ModTender has turned off all {n_off} mods. Start the game and do whatever made "
                              "the problem happen (load the save, open the menu, wait for the crash...).\n\n"
                              "Then come back and say whether it still happens.")
            self._show_list("", [])
        elif h.phase == "confirm":
            culprit = h.suspects[0]
            self.head.setText(f"Round {h.round} of {h.round}: last check")
            extra = n_off - 1
            self.body.setText(f"It looks like {h.name(culprit)}. To be sure, only that mod"
                              f"{f' and {extra} mod(s) that need it' if extra else ''} are off now, everything "
                              "else is on. Start the game once more and try again.")
            self._show_list("Turned off for this check:", h.testing_off)
        else:
            self.head.setText(f"Round {h.round} of about {total}")
            self.body.setText(f"{len(h.suspects)} mods could still be the cause. ModTender has turned {n_off} of "
                              "them off (plus any mods that need them). Start the game and try again.")
            self._show_list(f"Turned off this round ({n_off}):", h.testing_off)
        self.buttons.addWidget(button("Stop and put everything back", self._stop, "Danger"))
        self.buttons.addStretch()
        self.buttons.addWidget(button("It still happens", lambda: self._answer(True)))
        self.buttons.addWidget(button("The problem is gone", lambda: self._answer(False), "Primary"))

    def _show_list(self, label: str, names: list[str]):
        self.list_label.setVisible(bool(names))
        self.list.setVisible(bool(names))
        self.list_label.setText(label)
        self.list.setPlainText("\n".join(self.hunt.name(n) for n in names[:300]))

    # ------------------------------------------------------------ actions

    def _busy(self, fn):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return fn()
        finally:
            QApplication.restoreOverrideCursor()

    def _answer(self, still_happens: bool):
        try:
            self.hunt = self._busy(lambda: bisect.answer(self.game, self.hunt, still_happens))
        except Exception as exc:
            self.win.show_error("Couldn't move the mods for the next round", exc)
            return
        self.render()

    def _stop(self):
        self._finish([])

    def _finish(self, keep_off):
        problems = self._busy(lambda: bisect.stop(self.game, self.hunt, keep_off))
        if problems:
            self.win.show_error("Some mods couldn't be put back", "\n".join(problems))
        self.accept()
