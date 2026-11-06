"""The five pages: Dashboard, Mods, Issues, Backups, Settings."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QSplitter,
    QTableWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from ..core.issues import health_label, health_score
from ..core.report import human_size
from . import theme
from .widgets import SortItem, StatCard

if TYPE_CHECKING:
    from .main_window import MainWindow

SEVERITY_ICON = {"critical": "●  Critical", "warning": "●  Warning", "info": "●  Info"}


def _button(text: str, slot, primary=False, danger=False, tip="") -> QPushButton:
    b = QPushButton(text)
    if primary:
        b.setObjectName("Primary")
    elif danger:
        b.setObjectName("Danger")
    if tip:
        b.setToolTip(tip)
    b.clicked.connect(slot)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setWordWrap(False)
    t.horizontalHeader().setHighlightSections(False)
    return t


class Page(QWidget):
    title = ""

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.setObjectName("Page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(28, 24, 28, 20)
        self.root.setSpacing(14)
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        self.heading = QLabel(self.title, objectName="PageTitle")
        self.subheading = QLabel("", objectName="Muted")
        col.addWidget(self.heading)
        col.addWidget(self.subheading)
        head.addLayout(col)
        head.addStretch()
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        head.addLayout(self.actions)
        self.root.addLayout(head)

    def refresh(self):
        pass


# ---------------------------------------------------------------- Dashboard

class DashboardPage(Page):
    title = "Dashboard"

    def __init__(self, win):
        super().__init__(win)
        self.actions.addWidget(_button("Open mods folder", win.open_mods_folder))
        self.actions.addWidget(_button("Export report", win.export_report,
                                       tip="Save a text report you can share when asking for help"))
        self.actions.addWidget(_button("Back up now", win.create_backup))
        self.actions.addWidget(_button("Scan", win.start_scan, primary=True))

        grid = QGridLayout()
        grid.setSpacing(14)
        self.health = StatCard("Health")
        self.mods = StatCard("Mods")
        self.problems = StatCard("Issues")
        self.backup = StatCard("Last backup")
        for i, card in enumerate((self.health, self.mods, self.problems, self.backup)):
            grid.addWidget(card, 0, i)
        self.root.addLayout(grid)

        row = QHBoxLayout()
        row.addWidget(QLabel("Top issues", objectName="Section"))
        row.addStretch()
        row.addWidget(_button("View all issues", lambda: win.go("issues")))
        self.root.addLayout(row)
        self.issue_list = QListWidget()
        self.issue_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.issue_list.itemDoubleClicked.connect(lambda _: win.go("issues"))
        self.root.addWidget(self.issue_list, 1)

    def refresh(self):
        game, scan, issues = self.win.game, self.win.scan, self.win.issues
        if game is None:
            self.heading.setText("Welcome to ModTender")
            self.subheading.setText("No games found yet. Use '+ Add game' in the sidebar to pick a mods folder.")
            for card in (self.health, self.mods, self.problems, self.backup):
                card.set("-")
            self.issue_list.clear()
            return
        self.heading.setText(game.name)
        self.subheading.setText(str(game.mods_dir))
        if scan is None:
            for card in (self.health, self.mods, self.problems):
                card.set("-", "Not scanned yet")
            self.issue_list.clear()
            self.issue_list.addItem("Press Scan to check this game's mods.")
        else:
            score = health_score(issues)
            self.health.set(f"{score}", health_label(score), theme.score_color(score))
            enabled = sum(m.enabled for m in scan.mods)
            self.mods.set(str(enabled), f"enabled · {len(scan.mods) - enabled} disabled · "
                                        f"{human_size(sum(m.size for m in scan.mods if m.enabled))}")
            crit = sum(i.severity == "critical" for i in issues)
            warn = sum(i.severity == "warning" for i in issues)
            info = len(issues) - crit - warn
            color = theme.CRITICAL if crit else theme.WARNING if warn else theme.ACCENT
            self.problems.set(str(crit + warn), f"{crit} critical · {warn} warnings · {info} notes", color)
            self.issue_list.clear()
            if not issues:
                item = QListWidgetItem("✓  No problems found. Your mods look healthy.")
                item.setForeground(QColor(theme.ACCENT))
                self.issue_list.addItem(item)
            for issue in issues[:8]:
                mods = ", ".join(issue.mods[:2]) + (" …" if len(issue.mods) > 2 else "")
                item = QListWidgetItem(f"●  {issue.title}" + (f"  —  {mods}" if mods else ""))
                item.setForeground(QColor(theme.SEVERITY_COLORS[issue.severity]))
                item.setToolTip(issue.detail)
                self.issue_list.addItem(item)
        last = self.win.backups[0] if self.win.backups else None
        if last:
            self.backup.set(last.created.strftime("%b %d"), last.created.strftime("%H:%M") +
                            f" · {len(self.win.backups)} saved")
        else:
            self.backup.set("None", "Back up before you change anything big", theme.WARNING)


# ---------------------------------------------------------------- Mods

class ModsPage(Page):
    title = "Mods"
    COLS = ["Status", "Name", "Version", "Type", "Size", "Modified", "Issues"]

    def __init__(self, win):
        super().__init__(win)
        self.actions.addWidget(_button("Show in Explorer", self._reveal))
        self.actions.addWidget(_button("Disable", lambda: win.set_enabled(self.selected(), False),
                                       tip="Moves the mod out of the game's folder. Nothing is deleted."))
        self.actions.addWidget(_button("Enable", lambda: win.set_enabled(self.selected(), True), primary=True))

        bar = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Search mods…")
        self.search.textChanged.connect(self.refresh)
        self.filter = QComboBox()
        self.filter.addItems(["All mods", "Enabled", "Disabled", "With issues"])
        self.filter.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.filter)
        self.root.addLayout(bar)

        self.table = _table(self.COLS)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (0, 2, 3, 4, 5, 6):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._reveal)
        self.root.addWidget(self.table, 1)

    def selected(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        return [self.table.item(r, 1).data(Qt.ItemDataRole.UserRole) for r in sorted(rows)]

    def _reveal(self, *_):
        mods = self.selected()
        if mods:
            self.win.reveal(mods[0].path)

    def refresh(self):
        scan = self.win.scan
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        if scan is None:
            self.subheading.setText("Scan a game to see its mods.")
            return
        flagged: dict[str, int] = {}
        for issue in self.win.issues:
            for name in issue.mods:
                flagged[name] = flagged.get(name, 0) + 1
        text = self.search.text().strip().lower()
        mode = self.filter.currentIndex()
        shown = 0
        for m in scan.mods:
            if text and text not in m.name.lower() and text not in m.title.lower():
                continue
            if (mode == 1 and not m.enabled) or (mode == 2 and m.enabled) or (mode == 3 and m.name not in flagged):
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            status = "Game file" if m.protected else "Enabled" if m.enabled else "Disabled"
            cells = [
                SortItem(status),
                SortItem(m.display_name, m.display_name.lower()),
                SortItem(m.version or "-"),
                SortItem(m.kind.capitalize()),
                SortItem(human_size(m.size), m.size),
                SortItem(m.modified.strftime("%Y-%m-%d"), m.mtime),
                SortItem(str(flagged.get(m.name, "")) or "", flagged.get(m.name, 0)),
            ]
            cells[0].setForeground(QColor(theme.ACCENT if m.enabled else theme.MUTED))
            cells[1].setData(Qt.ItemDataRole.UserRole, m)
            cells[1].setToolTip(f"{m.name}\n{m.path}" + (f"\nby {m.author}" if m.author else ""))
            if m.name in flagged:
                cells[6].setForeground(QColor(theme.WARNING))
            if not m.enabled:
                for c in cells[1:]:
                    c.setForeground(QColor(theme.MUTED))
            for c, item in enumerate(cells):
                self.table.setItem(r, c, item)
            shown += 1
        self.table.setSortingEnabled(True)
        enabled = sum(m.enabled for m in scan.mods)
        self.subheading.setText(f"Showing {shown} of {len(scan.mods)} · {enabled} enabled")


# ---------------------------------------------------------------- Issues

class IssuesPage(Page):
    title = "Issues"

    def __init__(self, win):
        super().__init__(win)
        self.actions.addWidget(_button("Export report", win.export_report))
        self.actions.addWidget(_button("Show mod", self._reveal))
        self.actions.addWidget(_button("Re-scan", win.start_scan, primary=True))
        split = QSplitter(Qt.Orientation.Vertical)
        self.table = _table(["Severity", "Problem", "Affects"])
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setSizes([380, 200])
        self.root.addWidget(split, 1)

    def _current(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return self.table.item(rows[0].row(), 1).data(Qt.ItemDataRole.UserRole) if rows else None

    def _reveal(self):
        issue = self._current()
        if issue and issue.mods and self.win.scan:
            for m in self.win.scan.mods:
                if m.name == issue.mods[0]:
                    return self.win.reveal(m.path)
            self.win.reveal(self.win.game.mods_dir / issue.mods[0])

    def _show_detail(self):
        issue = self._current()
        if not issue:
            self.detail.clear()
            return
        color = theme.SEVERITY_COLORS[issue.severity]
        esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.detail.setHtml(
            f"<h3 style='color:{color}; margin:0'>{esc(issue.title)}</h3>"
            f"<p style='white-space:pre-wrap'>{esc(issue.detail)}</p>"
            f"<p><b style='color:{theme.ACCENT}'>How to fix:</b> {esc(issue.fix)}</p>"
        )

    def refresh(self):
        issues = self.win.issues
        self.table.setRowCount(0)
        self.detail.clear()
        if self.win.scan is None:
            self.subheading.setText("Scan a game to check for problems.")
            return
        crit = sum(i.severity == "critical" for i in issues)
        self.subheading.setText(f"{len(issues)} found · {crit} critical" if issues else "No problems found.")
        for issue in issues:
            r = self.table.rowCount()
            self.table.insertRow(r)
            sev = SortItem(SEVERITY_ICON[issue.severity])
            sev.setForeground(QColor(theme.SEVERITY_COLORS[issue.severity]))
            title = SortItem(issue.title)
            title.setData(Qt.ItemDataRole.UserRole, issue)
            affects = SortItem(", ".join(issue.mods) or "-")
            affects.setToolTip("\n".join(issue.mods))
            for c, item in enumerate((sev, title, affects)):
                self.table.setItem(r, c, item)
        if issues:
            self.table.selectRow(0)


# ---------------------------------------------------------------- Backups

class BackupsPage(Page):
    title = "Backups"

    def __init__(self, win):
        super().__init__(win)
        self.actions.addWidget(_button("Open backup folder", win.open_backup_folder))
        self.actions.addWidget(_button("Delete", self._delete, danger=True))
        self.actions.addWidget(_button("Restore", self._restore))
        self.actions.addWidget(_button("Back up now", win.create_backup, primary=True))
        self.table = _table(["Created", "Items", "Mods size", "Backup file"])
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        h = self.table.horizontalHeader()
        for c in (0, 1, 2):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.root.addWidget(self.table, 1)
        note = QLabel("Restoring never deletes anything: your current mods folder is renamed to "
                      "'mods.before-restore-…' next to the original, so you can always go back.",
                      objectName="Muted")
        note.setWordWrap(True)
        self.root.addWidget(note)

    def _current(self):
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole) if rows else None

    def _restore(self):
        b = self._current()
        if b:
            self.win.restore_backup(b)

    def _delete(self):
        b = self._current()
        if b:
            self.win.delete_backup(b)

    def refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        if self.win.game is None:
            self.subheading.setText("")
            return
        self.subheading.setText(f"{len(self.win.backups)} backups · keeping the newest "
                                f"{self.win.settings.keep_backups} · {self.win.settings.backup_root}")
        for b in self.win.backups:
            r = self.table.rowCount()
            self.table.insertRow(r)
            created = SortItem(b.created.strftime("%Y-%m-%d  %H:%M"), b.created.timestamp())
            created.setData(Qt.ItemDataRole.UserRole, b)
            items = [created, SortItem(str(b.mod_count), b.mod_count),
                     SortItem(human_size(b.total_size), b.total_size), SortItem(b.path.name)]
            for c, item in enumerate(items):
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.SortOrder.DescendingOrder)


# ---------------------------------------------------------------- Settings

class SettingsPage(Page):
    title = "Settings"

    def __init__(self, win):
        super().__init__(win)
        self._loading = True
        self.subheading.setText("Saved automatically.")
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        row = QHBoxLayout()
        self.backup_dir = QLineEdit(placeholderText="Default: %LOCALAPPDATA%\\ModTender\\backups")
        self.backup_dir.editingFinished.connect(self._save)
        row.addWidget(self.backup_dir, 1)
        row.addWidget(_button("Browse…", self._browse))
        form.addRow("Backup folder", row)

        self.keep = QSpinBox(minimum=1, maximum=100)
        self.keep.valueChanged.connect(self._save)
        form.addRow("Backups to keep per game", self.keep)

        self.deep = QCheckBox("Deep check: verify every byte of every archive (slower, catches subtle damage)")
        self.deep.toggled.connect(self._save)
        form.addRow("Scanning", self.deep)
        self.root.addLayout(form)

        self.root.addWidget(QLabel("Games you added", objectName="Section"))
        self.custom = QListWidget()
        self.custom.setMaximumHeight(160)
        self.root.addWidget(self.custom)
        row2 = QHBoxLayout()
        row2.addWidget(_button("+ Add game", win.add_custom_game))
        row2.addWidget(_button("Remove selected", self._remove_custom, danger=True))
        row2.addStretch()
        self.root.addLayout(row2)

        self.root.addWidget(QLabel("Where ModTender keeps its files", objectName="Section"))
        from ..core import paths
        info = QLabel(f"Data and disabled mods: {paths.DATA_DIR}\n"
                      "Disabled mods are moved here so the game can't see them. Enabling moves them back.",
                      objectName="Muted")
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.root.addWidget(info)
        self.root.addStretch()

    def refresh(self):
        self._loading = True
        s = self.win.settings
        self.backup_dir.setText(s.backup_dir)
        self.keep.setValue(s.keep_backups)
        self.deep.setChecked(s.deep_check)
        self.custom.clear()
        for g in s.custom_games:
            item = QListWidgetItem(f"{g['name']}  —  {g['path']}")
            item.setData(Qt.ItemDataRole.UserRole, g["id"])
            self.custom.addItem(item)
        self._loading = False

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose backup folder", self.backup_dir.text())
        if folder:
            self.backup_dir.setText(folder)
            self._save()

    def _save(self, *_):
        if self._loading:
            return
        s = self.win.settings
        s.backup_dir = self.backup_dir.text().strip()
        s.keep_backups = self.keep.value()
        s.deep_check = self.deep.isChecked()
        self.win.save_settings()

    def _remove_custom(self):
        item = self.custom.currentItem()
        if item:
            self.win.remove_custom_game(item.data(Qt.ItemDataRole.UserRole))
