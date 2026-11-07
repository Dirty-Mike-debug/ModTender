"""Space saver window: how much disk space shared mod files could free, and doing it (or undoing it)."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QTableWidgetItem, QVBoxLayout

from ..core import spacesaver
from .pages import button, make_table
from .widgets import SortItem


def _size(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit not in ("bytes",) else f"{n} bytes"
        n /= 1024
    return f"{n:.1f} GB"


class SpaceDialog(QDialog):
    def __init__(self, win, plan):
        super().__init__(win)
        self.win, self.plan = win, plan
        self.setWindowTitle("Space saver")
        self.resize(860, 560)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        games = sorted({g for grp in plan.groups for g in grp.games})
        if plan.groups:
            head = (f"You can free {_size(plan.saving)}: {len(plan.groups)} mod file"
                    f"{'s are' if len(plan.groups) != 1 else ' is'} stored more than once across "
                    f"{', '.join(games)}.")
        else:
            head = "Nothing to share right now: no identical mod files are stored twice."
        title = QLabel(head, objectName="Section", wordWrap=True)
        lay.addWidget(title)
        notes = ["Each pack keeps its own normal-looking file, but identical files are stored on disk only once. "
                 "If a launcher updates a mod later, that pack simply gets its own copy again."]
        if plan.already_shared:
            notes.append(f"Already saving {_size(plan.already_shared)} from earlier.")
        if plan.skipped_onedrive:
            notes.append(f"{plan.skipped_onedrive} mod files in OneDrive folders were left alone (OneDrive doesn't "
                         "support this).")
        notes.append("Windows Explorer will still show each folder's full size; the free space on your drive is "
                     "what goes up.")
        lay.addWidget(QLabel("  ".join(notes), wordWrap=True, objectName="Muted"))
        self.table = make_table(["Mod", "Size", "Copies", "Saves", "Used by"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3, 4):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setRowCount(len(plan.groups))
        for r, g in enumerate(plan.groups):
            for c, item in enumerate((QTableWidgetItem(g.title), SortItem(_size(g.size), g.size),
                                      SortItem(str(len(g.files)), len(g.files)), SortItem(_size(g.saving), g.saving),
                                      QTableWidgetItem(", ".join(g.games)))):
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        if spacesaver.shared_count():
            row.addWidget(button("Undo space saver", self._undo,
                                 tip="Turn every shared file back into its own separate copy"))
        row.addStretch()
        row.addWidget(button("Close", self.reject))
        if plan.groups:
            row.addWidget(button(f"Free {_size(plan.saving)}", self._apply, "Primary", "save"))
        lay.addLayout(row)

    def _apply(self):
        def done(result):
            saved, problems = result
            text = f"Freed {_size(saved)}."
            if problems:
                text += f"\n\n{len(problems)} file(s) were skipped:\n" + "\n".join(problems[:10])
            QMessageBox.information(self.win, "Space saver", text)
        self.accept()
        self.win._run("Sharing identical mod files…", lambda progress: spacesaver.apply(self.plan, progress),
                      on_done=done)

    def _undo(self):
        n = spacesaver.shared_count()
        if QMessageBox.question(self, "Space saver", f"Make {n} shared file{'s' if n != 1 else ''} separate copies "
                                "again? This uses the disk space again.") != QMessageBox.StandardButton.Yes:
            return

        def done(result):
            count, problems = result
            text = f"Made {count} file(s) separate again."
            if problems:
                text += f"\n\n{len(problems)} couldn't be changed:\n" + "\n".join(problems[:10])
            QMessageBox.information(self.win, "Space saver", text)
        self.accept()
        self.win._run("Making separate copies…", lambda progress: spacesaver.undo(progress), on_done=done)
