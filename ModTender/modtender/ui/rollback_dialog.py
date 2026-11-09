"""Window listing mod updates that can be undone (the update is on, its old version is in disabled mods)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QHeaderView, QLabel, QTableWidgetItem, QVBoxLayout

from .pages import button, make_table


class RollbackDialog(QDialog):
    COLS = ["", "Mod", "Now", "Goes back to", "Files"]

    def __init__(self, parent, game, items):
        super().__init__(parent)
        self.items = items
        self.chosen = []
        self.setWindowTitle("Undo mod updates")
        self.resize(880, 520)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        head = QLabel(f"{len(items)} updated mod{'s' if len(items) != 1 else ''} in {game.name} can go back")
        head.setObjectName("Section")
        lay.addWidget(head)
        info = QLabel("These mods have an older version waiting in ModTender's disabled mods. Going back turns the "
                      "update off and the old version on. Nothing is deleted, so you can switch again later.",
                      wordWrap=True)
        info.setObjectName("Muted")
        lay.addWidget(info)
        self.table = make_table(self.COLS)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (0, 2, 3, 4):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setRowCount(len(items))
        for r, it in enumerate(items):
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            tick.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(r, 0, tick)
            self.table.setItem(r, 1, QTableWidgetItem(it.title))
            self.table.setItem(r, 2, QTableWidgetItem(it.from_version))
            self.table.setItem(r, 3, QTableWidgetItem(it.to_version))
            files = QTableWidgetItem(f"{it.new.name}  →  {it.old.name}")
            files.setToolTip(f"Turns off {it.new.name}\nTurns on {it.old.name}")
            self.table.setItem(r, 4, files)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(button("Select all", lambda: self._tick(True)))
        row.addWidget(button("Select none", lambda: self._tick(False)))
        row.addStretch()
        row.addWidget(button("Close", self.reject))
        go = button("Go back to old versions", self._accept, "Primary", "update")
        go.setEnabled(bool(items))
        row.addWidget(go)
        lay.addLayout(row)

    def _tick(self, on: bool):
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def _accept(self):
        self.chosen = [it for r, it in enumerate(self.items)
                       if self.table.item(r, 0).checkState() == Qt.CheckState.Checked]
        if self.chosen:
            self.accept()
