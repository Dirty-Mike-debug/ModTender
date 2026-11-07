"""Compare your mods with a server, a friend's setup or a modpack, and fix the differences."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMessageBox,
    QTableWidgetItem, QVBoxLayout,
)

from ..core import modlist
from . import theme
from .pages import button, make_table

INTRO = ("Open the mod list you want to match: a setup file a friend shared from ModTender, a Farming "
         "Simulator server's stats file or link, a savegame's careerSavegame.xml, or a Modrinth modpack "
         "(.mrpack). You can also paste a plain list of mod names.")

NOTES = {
    "fs25": "Extra mods don't stop you joining a Farming Simulator server: the game only loads the ones the "
            "server uses. Missing mods and different versions do.",
    "fs22": "Extra mods don't stop you joining a Farming Simulator server: the game only loads the ones the "
            "server uses. Missing mods and different versions do.",
    "minecraft": "Mods that add blocks, items or mobs must match the server exactly. Extra client-only mods "
                 "(minimaps, shaders, performance mods) are usually fine.",
}


class CompareDialog(QDialog):
    COLS = ["Status", "Mod", "You have", "List has"]

    def __init__(self, win, game, mods):
        super().__init__(win)
        self.win, self.game, self.mods = win, game, mods
        self.result = None
        self.changed = False
        self.setWindowTitle("Match mods")
        self.resize(900, 600)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        self.head = QLabel(f"Match your {game.name} mods with someone else's", objectName="Section")
        lay.addWidget(self.head)
        self.info = QLabel(INTRO, wordWrap=True, objectName="Muted")
        lay.addWidget(self.info)
        row = QHBoxLayout()
        row.addWidget(button("Open a file…", self._open_file, "Primary", "folder"))
        row.addWidget(button("Paste a list or link…", self._paste, icon_name="report"))
        row.addStretch()
        lay.addLayout(row)
        self.note = QLabel(NOTES.get(game.definition.id, ""), wordWrap=True, objectName="Muted")
        self.note.hide()
        lay.addWidget(self.note)
        self.table = make_table(self.COLS)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (0, 2, 3):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.hide()
        lay.addWidget(self.table, 1)
        lay.addStretch()
        self.actions = QHBoxLayout()
        lay.addLayout(self.actions)
        self._draw_actions()

    # ------------------------------------------------------------ loading

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open a mod list", str(Path.home() / "Downloads"),
            "Mod lists (*.modtender *.json *.xml *.mrpack *.txt);;All files (*)")
        if path:
            self._load(lambda: modlist.read_list(path))

    def _paste(self):
        text, ok = QInputDialog.getMultiLineText(
            self, "Paste a mod list",
            "Paste mod names (one per line), a Farming Simulator server's stats link "
            "(…/feed/dedicated-server-stats.xml?code=…), or the contents of a mod list file:")
        if ok and text.strip():
            self._load(lambda: modlist.read_list(text, from_text=True))

    def _load(self, read):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            listed = read()
        except modlist.ListError as exc:
            listed, error = None, str(exc)
        finally:
            QApplication.restoreOverrideCursor()
        if listed is None:
            QMessageBox.warning(self, "Match mods", error)
            return
        self.listed = listed
        if listed.game_id and not _same_game(listed.game_id, self.game.definition.id):
            QMessageBox.information(self, "Match mods", f"This list looks like it's for a different game "
                                                        f"({listed.game_id}). Comparing anyway.")
        self.result = modlist.compare(listed, self.mods)
        self._draw()

    # ------------------------------------------------------------ results

    def _draw(self):
        c = self.result
        self.head.setText(modlist.summary(c))
        extra = ""
        if self.listed.mc_version and self.game.definition.id == "minecraft":
            from ..core.minecraft import instance_info
            loader, mc = instance_info(self.game.mods_dir)
            if mc and mc != self.listed.mc_version:
                extra = f"  Note: the list is for Minecraft {self.listed.mc_version}, this instance is {mc}."
        self.info.setText(f"Compared with {self.listed.source}.{extra}")
        self.note.setVisible(bool(self.note.text()) and not c.matches)
        rows = ([("Missing", "critical", m.title or m.name, "—", m.version or m.name) for m in c.missing]
                + [("Turned off here", "warning", m.mod.display_name, "Off", m.listed.version or "On")
                   for m in c.turned_off]
                + [("Different version", "warning", m.mod.display_name, m.mod.version or m.mod.name,
                    m.listed.version or m.listed.name) for m in c.other_version]
                + [("Extra", "info", m.display_name, m.version or "On", "—") for m in c.extra]
                + [("Matches", "", m.mod.display_name, m.mod.version or "On", m.listed.version or "On")
                   for m in c.same])
        self.table.setRowCount(len(rows))
        for r, (status, sev, name, have, want) in enumerate(rows):
            item = QTableWidgetItem(f"●  {status}" if sev else status)
            if sev:
                item.setForeground(QColor(theme.SEVERITY_COLORS[sev]))
            for col, value in enumerate((item, QTableWidgetItem(name), QTableWidgetItem(str(have)),
                                         QTableWidgetItem(str(want)))):
                self.table.setItem(r, col, value)
        self.table.show()
        self._draw_actions()

    def _draw_actions(self):
        while self.actions.count():
            w = self.actions.takeAt(0).widget()
            if w:
                w.deleteLater()
        c = self.result
        if c:
            self.actions.addWidget(button("Copy as text", self._copy, icon_name="report",
                                          tip="Copy the differences to paste into a chat"))
            if c.extra:
                self.actions.addWidget(button(f"Turn off {len(c.extra)} extra", self._turn_off_extra,
                                              tip="Turn off mods the list doesn't have. You can turn them back on."))
            findable = [m for m in c.missing if not m.download]
            if findable:
                self.actions.addWidget(button(f"Find {len(findable)} missing online", self._find_missing,
                                              icon_name="external"))
        self.actions.addStretch()
        self.actions.addWidget(button("Close", self.accept))
        if c:
            downloadable = [m for m in c.missing if m.download]
            if downloadable:
                self.actions.addWidget(button(f"Download {len(downloadable)} missing", self._download,
                                              "Primary", "update"))
            if c.turned_off:
                self.actions.addWidget(button(f"Turn on {len(c.turned_off)}", self._turn_on, "Primary", "fix"))

    # ------------------------------------------------------------ fixes

    def _copy(self):
        QApplication.clipboard().setText(modlist.as_text(self.result))
        self.win.status("Copied the differences.")

    def _refresh_mods(self):
        from ..core.scanner import scan_game
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.mods = scan_game(self.game).mods
        finally:
            QApplication.restoreOverrideCursor()
        self.changed = True
        self.result = modlist.compare(self.listed, self.mods)
        self._draw()

    def _turn_on(self):
        from ..core import manager
        problems = []
        for m in self.result.turned_off:
            try:
                manager.enable_mod(self.game, m.mod)
            except Exception as exc:
                problems.append(f"{m.mod.display_name}: {exc}")
        if problems:
            QMessageBox.warning(self, "Match mods", "Some mods couldn't be turned on:\n\n" + "\n".join(problems))
        self._refresh_mods()

    def _turn_off_extra(self):
        from ..core import manager
        n = len(self.result.extra)
        if QMessageBox.question(self, "Match mods", f"Turn off {n} mod{'s' if n != 1 else ''} that the list "
                                "doesn't have? They're moved out of the game's folder, not deleted, and you can "
                                "turn them back on from the Mods page.") != QMessageBox.StandardButton.Yes:
            return
        for m in self.result.extra:
            try:
                manager.disable_mod(self.game, m)
            except Exception:
                pass
        self._refresh_mods()

    def _find_missing(self):
        items = [m for m in self.result.missing if not m.download]
        for item in items[:5]:
            QDesktopServices.openUrl(QUrl(modlist.search_url(self.game, item)))
        if len(items) > 5:
            self.win.status(f"Opened the first 5 of {len(items)}. Use Copy as text for the full list.")

    def _download(self):
        items = [m for m in self.result.missing if m.download]

        def done(result):
            ok, problems = result
            if problems:
                QMessageBox.warning(self, "Match mods",
                                    f"Downloaded {len(ok)}. These failed:\n\n" + "\n".join(problems[:20]))
            self._refresh_mods()

        self.win._run(f"Downloading {len(items)} mod(s)…",
                      lambda progress: modlist.download_missing(self.game, items, progress), on_done=done)


def _same_game(listed: str, current: str) -> bool:
    if listed == current:
        return True
    return listed == "fs" and current in ("fs25", "fs22")
