"""Window listing mod updates found on Modrinth, so the user picks which to install."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QHeaderView, QLabel, QTableWidgetItem, QVBoxLayout

from . import theme
from .pages import button, make_table


class ModUpdatesDialog(QDialog):
    COLS = ["", "Mod", "Installed", "New version", "Channel", "Released"]

    def __init__(self, parent, game, result):
        super().__init__(parent)
        self.result_info = result
        self.chosen = []
        self.setWindowTitle("Mod updates")
        self.resize(900, 560)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        n = len(result.updates)
        loader = {"neoforge": "NeoForge", "forge": "Forge", "fabric": "Fabric", "quilt": "Quilt"}.get(result.loader,
                                                                                                    result.loader)
        head = QLabel(f"{n} update{'s' if n != 1 else ''} for {game.name}" if n else f"Everything is up to date")
        head.setObjectName("Section")
        lay.addWidget(head)
        sub = (f"Checked {result.checked} mods for {loader} on Minecraft {result.mc_version}"
               f"{' (worked out from the file names)' if result.guessed_version else ''}. "
               f"{result.known} of them are on Modrinth; mods only on CurseForge can't be checked yet.")
        info = QLabel(sub, wordWrap=True)
        info.setObjectName("Muted")
        lay.addWidget(info)
        if game.source == "curseforge" and n:
            warn = QLabel("This is a CurseForge modpack. Packs are tested with these exact versions, so "
                          "updating mods yourself can break it, and CurseForge may put the old versions back "
                          "when the pack updates. Only update a mod if you need a fix from it.", wordWrap=True)
            warn.setStyleSheet(f"color: {theme.SEVERITY_COLORS['warning']};")
            lay.addWidget(warn)

        self.table = make_table(self.COLS)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (0, 2, 3, 4, 5):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setRowCount(n)
        for r, u in enumerate(result.updates):
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            # Pre-tick stable releases outside modpacks; betas and modpack mods are opt-in.
            on = u.channel == "release" and game.source != "curseforge"
            tick.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, tick)
            name = QTableWidgetItem(u.title)
            name.setData(Qt.ItemDataRole.UserRole, u)
            name.setToolTip(u.mod_name)
            self.table.setItem(r, 1, name)
            self.table.setItem(r, 2, QTableWidgetItem(u.current))
            self.table.setItem(r, 3, QTableWidgetItem(u.new))
            ch = QTableWidgetItem(u.channel.capitalize())
            if u.channel != "release":
                ch.setForeground(QColor(theme.SEVERITY_COLORS["warning"]))
                ch.setToolTip("Not a stable release yet: may have bugs")
            self.table.setItem(r, 4, ch)
            self.table.setItem(r, 5, QTableWidgetItem(u.published))
        lay.addWidget(self.table, 1)

        note = QLabel("Old versions are moved to ModTender's disabled mods, so you can turn them back on "
                      "from the Mods page if an update causes problems.", wordWrap=True)
        note.setObjectName("Muted")
        lay.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(button("Select all", lambda: self._tick_all(True)))
        row.addWidget(button("Select none", lambda: self._tick_all(False)))
        row.addWidget(button("Open on Modrinth", self._open_page, icon_name="external"))
        row.addStretch()
        row.addWidget(button("Close", self.reject))
        self.go = button("Update selected", self._accept, "Primary", "update")
        self.go.setEnabled(bool(n))
        row.addWidget(self.go)
        lay.addLayout(row)

    def _rows(self):
        return [self.table.item(r, 1).data(Qt.ItemDataRole.UserRole) for r in range(self.table.rowCount())]

    def _tick_all(self, on: bool):
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def _open_page(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}) or [0]
        if self.table.rowCount():
            u = self.table.item(rows[0], 1).data(Qt.ItemDataRole.UserRole)
            QDesktopServices.openUrl(QUrl(u.page))

    def _accept(self):
        self.chosen = [u for r, u in enumerate(self._rows())
                       if self.table.item(r, 0).checkState() == Qt.CheckState.Checked]
        if self.chosen:
            self.accept()
