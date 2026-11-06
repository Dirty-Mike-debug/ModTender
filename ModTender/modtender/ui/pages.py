"""The five pages: Dashboard, Mods, Issues, Backups, Settings."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QTableWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core.issues import health_label, health_score
from ..core.report import human_size
from . import theme
from .widgets import HealthCard, SortItem, StatCard, divider, icon

if TYPE_CHECKING:
    from .main_window import MainWindow

SEVERITY_TEXT = {"critical": "Critical", "warning": "Warning", "info": "Note"}


def button(text: str, slot, kind: str = "", icon_name: str = "", tip: str = "") -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)  # Primary | Danger | Ghost
    if icon_name:
        color = None
        if kind == "Primary":
            color = "#0b1410" if QColor(theme.ACCENT).lightness() > 150 else "#ffffff"
        elif kind == "Danger":
            color = theme.CRITICAL
        b.setIcon(icon(icon_name, color))
        b.setIconSize(QSize(15, 15))
    if tip:
        b.setToolTip(tip)
    b.clicked.connect(slot)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(36)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setWordWrap(False)
    t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    h = t.horizontalHeader()
    h.setHighlightSections(False)
    h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return t


def severity_item(severity: str) -> SortItem:
    order = {"critical": 0, "warning": 1, "info": 2}[severity]
    item = SortItem(f"●  {SEVERITY_TEXT[severity]}", order)
    item.setForeground(QColor(theme.SEVERITY_COLORS[severity]))
    return item


class Page(QWidget):
    title = ""

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.setObjectName("Page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(32, 26, 32, 22)
        self.root.setSpacing(16)
        head = QHBoxLayout()
        head.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.heading = QLabel(self.title, objectName="PageTitle")
        self.subheading = QLabel("", objectName="Muted")
        self.subheading.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        col.addWidget(self.heading)
        col.addWidget(self.subheading)
        head.addLayout(col, 1)
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
        self.actions.addWidget(button("Open folder", win.open_mods_folder, icon_name="folder"))
        self.actions.addWidget(button("Report", win.export_report, icon_name="report",
                                      tip="Save a text report you can share when asking for help"))
        self.actions.addWidget(button("Back up", win.create_backup, icon_name="save"))
        self.actions.addWidget(button("Scan", win.start_scan, "Primary", "scan"))

        grid = QGridLayout()
        grid.setSpacing(14)
        self.health = HealthCard()
        self.mods = StatCard("Mods")
        self.problems = StatCard("Issues")
        self.backup = StatCard("Last backup")
        grid.addWidget(self.health, 0, 0)
        grid.addWidget(self.mods, 0, 1)
        grid.addWidget(self.problems, 0, 2)
        grid.addWidget(self.backup, 0, 3)
        grid.setColumnStretch(0, 5)
        for c in (1, 2, 3):
            grid.setColumnStretch(c, 4)
        self.root.addLayout(grid)

        row = QHBoxLayout()
        row.addWidget(QLabel("Top issues", objectName="Section"))
        row.addStretch()
        self.fix_all = button("Fix all", win.fix_all, "Primary", "fix",
                              tip="Apply every safe automatic fix. Nothing is deleted.")
        row.addWidget(self.fix_all)
        row.addWidget(button("View all", lambda: win.go("issues")))
        self.root.addLayout(row)
        self.issue_table = make_table(["Severity", "Problem", "Affects"])
        self.issue_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        h = self.issue_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.issue_table.cellDoubleClicked.connect(lambda *_: win.go("issues"))
        self.empty = QLabel("", objectName="Muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.root.addWidget(self.issue_table, 1)
        self.root.addWidget(self.empty)

    def _message(self, text: str, color: str | None = None):
        self.issue_table.hide()
        self.empty.setText(text)
        self.empty.setStyleSheet(f"color: {color}; font-size: 10.5pt; padding: 30px;" if color else "padding: 30px;")
        self.empty.show()

    def refresh(self):
        game, scan, issues = self.win.game, self.win.scan, self.win.issues
        self.issue_table.setRowCount(0)
        self.fix_all.setVisible(any(i.fixable and i.safe for i in issues))
        if game is None:
            self.heading.setText("Welcome to ModTender")
            self.subheading.setText("No games found yet. Use 'Add game' in the sidebar to pick a mods folder.")
            self.health.set(None, "–")
            for card in (self.mods, self.problems, self.backup):
                card.set("–")
            self._message("Add a game to get started.")
            return
        self.heading.setText(game.name)
        self.subheading.setText(str(game.mods_dir))
        if scan is None:
            self.health.set(None, "Not scanned", "Press Scan to check your mods")
            for card in (self.mods, self.problems):
                card.set("–", "Not scanned yet")
            self._message("Press Scan to check this game's mods.")
        else:
            score = health_score(issues)
            self.health.set(score, health_label(score), f"Checked {scan.scanned_at:%H:%M}")
            enabled = sum(m.enabled for m in scan.mods)
            self.mods.set(str(enabled), f"enabled · {len(scan.mods) - enabled} disabled · "
                                        f"{human_size(sum(m.size for m in scan.mods if m.enabled))}")
            crit = sum(i.severity == "critical" for i in issues)
            warn = sum(i.severity == "warning" for i in issues)
            info = len(issues) - crit - warn
            color = theme.CRITICAL if crit else theme.WARNING if warn else theme.ACCENT
            self.problems.set(str(crit + warn), f"{crit} critical · {warn} warnings · {info} notes", color)
            if not issues:
                self._message("✓  No problems found. Your mods look healthy.", theme.ACCENT)
            else:
                self.empty.hide()
                self.issue_table.show()
                for issue in issues[:10]:
                    r = self.issue_table.rowCount()
                    self.issue_table.insertRow(r)
                    mods = ", ".join(issue.mods[:3]) + (" …" if len(issue.mods) > 3 else "")
                    title = SortItem(issue.title)
                    title.setToolTip(issue.detail)
                    for c, item in enumerate((severity_item(issue.severity), title, SortItem(mods or "–"))):
                        self.issue_table.setItem(r, c, item)
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
        self.actions.addWidget(button("Show in Explorer", self._reveal, icon_name="folder"))
        self.actions.addWidget(button("Disable", lambda: win.set_enabled(self.selected(), False),
                                      tip="Moves the mod out of the game's folder. Nothing is deleted."))
        self.actions.addWidget(button("Enable", lambda: win.set_enabled(self.selected(), True), "Primary"))

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit(placeholderText="Search by name or title")
        self.search.addAction(icon("search", theme.MUTED), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.filter = QComboBox()
        self.filter.addItems(["All mods", "Enabled", "Disabled", "With issues"])
        self.filter.setMinimumWidth(150)
        self.filter.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.filter)
        self.root.addLayout(bar)

        self.table = make_table(self.COLS)
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
            n_issues = flagged.get(m.name, 0)
            cells = [
                SortItem(f"●  {status}", status),
                SortItem(m.display_name, m.display_name.lower()),
                SortItem(m.version or "–"),
                SortItem(m.kind.capitalize()),
                SortItem(human_size(m.size), m.size),
                SortItem(m.modified.strftime("%Y-%m-%d"), m.mtime),
                SortItem(f"⚠  {n_issues}" if n_issues else "", n_issues),
            ]
            cells[0].setForeground(QColor(theme.ACCENT if m.enabled else theme.MUTED))
            cells[1].setData(Qt.ItemDataRole.UserRole, m)
            cells[1].setToolTip(f"{m.name}\n{m.path}" + (f"\nby {m.author}" if m.author else ""))
            if n_issues:
                cells[6].setForeground(QColor(theme.WARNING))
            if not m.enabled:
                for c in cells[1:6]:
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
        self.actions.addWidget(button("Report", win.export_report, icon_name="report"))
        self.actions.addWidget(button("Show mod", self._reveal, icon_name="folder"))
        self.actions.addWidget(button("Re-scan", win.start_scan, icon_name="scan"))
        self.fix_one = button("Fix", self._fix, icon_name="fix", tip="Apply the fix for the selected issue")
        self.actions.addWidget(self.fix_one)
        self.fix_all = button("Fix all", win.fix_all, "Primary", "fix",
                              tip="Apply every safe automatic fix. Nothing is deleted.")
        self.actions.addWidget(self.fix_all)
        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        self.table = make_table(["Severity", "Problem", "Affects", "Fix"])
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.table.cellDoubleClicked.connect(lambda *_: self._fix())
        self.detail = QTextBrowser()
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setSizes([380, 210])
        self.root.addWidget(split, 1)

    def _current(self):
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 1).data(Qt.ItemDataRole.UserRole) if rows else None

    def _fix(self):
        issue = self._current()
        if issue:
            self.win.fix_issue(issue)

    def _reveal(self):
        issue = self._current()
        if issue and issue.mods and self.win.scan:
            for m in self.win.scan.mods:
                if m.name == issue.mods[0]:
                    return self.win.reveal(m.path)
            self.win.reveal(self.win.game.mods_dir / issue.mods[0])

    def _show_detail(self):
        issue = self._current()
        self.fix_one.setEnabled(bool(issue and issue.fixable))
        if not issue:
            self.detail.clear()
            return
        color = theme.SEVERITY_COLORS[issue.severity]
        esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.detail.setHtml(
            f"<div style='margin:6px'>"
            f"<span style='color:{color}; font-weight:600'>{SEVERITY_TEXT[issue.severity].upper()}</span>"
            f"<h3 style='margin:4px 0 10px 0'>{esc(issue.title)}</h3>"
            f"<p style='color:{theme.TEXT}'>{esc(issue.detail)}</p>"
            f"<p style='margin-top:12px'><span style='color:{theme.ACCENT}; font-weight:600'>How to fix</span><br>"
            f"{esc(issue.fix)}</p>"
            + (f"<p style='margin-top:12px'><span style='color:{theme.ACCENT}; font-weight:600'>The Fix button will</span><br>"
               f"{esc(issue.action_label)}" + ("" if issue.safe else
               f"<br><span style='color:{theme.MUTED}'>Not included in Fix all, because this one needs your judgement.</span>")
               + "</p>" if issue.fixable else
               f"<p style='margin-top:12px; color:{theme.MUTED}'>No automatic fix for this one. Follow the steps above.</p>")
            + "</div>"
        )

    def refresh(self):
        issues = self.win.issues
        self.table.setRowCount(0)
        self.detail.clear()
        if self.win.scan is None:
            self.subheading.setText("Scan a game to check for problems.")
            return
        crit = sum(i.severity == "critical" for i in issues)
        auto = sum(i.fixable and i.safe for i in issues)
        self.fix_all.setEnabled(auto > 0)
        self.subheading.setText(f"{len(issues)} found · {crit} critical · {auto} can be fixed automatically"
                                if issues else "No problems found.")
        for issue in issues:
            r = self.table.rowCount()
            self.table.insertRow(r)
            title = SortItem(issue.title)
            title.setData(Qt.ItemDataRole.UserRole, issue)
            affects = SortItem(", ".join(issue.mods) or "–")
            affects.setToolTip("\n".join(issue.mods))
            fix = SortItem("Auto-fix" if issue.fixable and issue.safe else "Fix button" if issue.fixable else "Manual",
                           0 if issue.fixable and issue.safe else 1 if issue.fixable else 2)
            fix.setForeground(QColor(theme.ACCENT if issue.fixable else theme.MUTED))
            for c, item in enumerate((severity_item(issue.severity), title, affects, fix)):
                self.table.setItem(r, c, item)
        if issues:
            self.table.selectRow(0)
        else:
            self.fix_one.setEnabled(False)


# ---------------------------------------------------------------- Backups

class BackupsPage(Page):
    title = "Backups"

    def __init__(self, win):
        super().__init__(win)
        self.actions.addWidget(button("Open folder", win.open_backup_folder, icon_name="folder"))
        self.actions.addWidget(button("Quarantine", win.open_quarantine_folder, icon_name="folder",
                                      tip="Files that Fix moved out of your mods folder"))
        self.actions.addWidget(button("Delete", self._delete, "Danger"))
        self.actions.addWidget(button("Restore", self._restore))
        self.actions.addWidget(button("Back up now", win.create_backup, "Primary", "save"))
        self.table = make_table(["Created", "Items", "Mods size", "Backup file"])
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        h = self.table.horizontalHeader()
        for c in (0, 1, 2):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.root.addWidget(self.table, 1)
        note = QLabel("Restoring never deletes anything: your current mods folder is renamed to "
                      "'mods.before-restore-…' next to the original, so you can always go back. "
                      "Files that Fix moves out of your mods folder go to Quarantine.",
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

class ColorButton(QPushButton):
    """A button that shows a color and opens a picker."""

    def __init__(self, color: str, on_pick, title: str):
        super().__init__()
        self.color, self.on_pick, self.title = color, on_pick, title
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(84, 28)
        self._paint()
        self.clicked.connect(self._pick)

    def _paint(self):
        text = "#0b1410" if QColor(self.color).lightness() > 150 else "#ffffff"
        self.setText(self.color.upper())
        self.setStyleSheet(f"background: {self.color}; color: {text}; border: 1px solid {theme.BORDER}; "
                           f"border-radius: 6px; font-size: 8.5pt; padding: 0;")

    def _pick(self):
        picked = QColorDialog.getColor(QColor(self.color), self, self.title)
        if picked.isValid():
            self.on_pick(picked.name())


class SettingsPage(Page):
    title = "Settings"

    def __init__(self, win):
        super().__init__(win)
        self._loading = True
        self.subheading.setText("Changes are saved automatically.")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget(objectName="ScrollBody")
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(0, 0, 12, 0)
        self.body.setSpacing(14)
        scroll.setWidget(body)
        self.root.addWidget(scroll, 1)

        self._build_appearance()
        self.body.addWidget(divider())
        self._build_general()
        self.body.addWidget(divider())
        self._build_games()
        self.body.addWidget(divider())
        self._build_updates()
        self.body.addStretch()

    # --- sections

    def _section(self, title: str, hint: str = ""):
        self.body.addWidget(QLabel(title, objectName="Section"))
        if hint:
            h = QLabel(hint, objectName="Muted")
            h.setWordWrap(True)
            self.body.addWidget(h)

    def _build_appearance(self):
        self._section("Appearance", "Pick a theme, then make any color your own.")
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.preset = QComboBox()
        self.preset.addItems(list(theme.PRESETS))
        self.preset.setMinimumWidth(180)
        self.preset.currentTextChanged.connect(self._preset_changed)
        form.addRow("Theme", self.preset)

        swatches = QHBoxLayout()
        swatches.setSpacing(8)
        for color in theme.ACCENT_SWATCHES:
            b = QPushButton(objectName="Swatch")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            ring = theme.TEXT if color.lower() == theme.ACCENT.lower() else "transparent"
            b.setStyleSheet(f"QPushButton#Swatch {{ background: {color}; border: 2px solid {ring}; }}")
            b.setToolTip(color)
            b.clicked.connect(lambda _=False, c=color: self.win.set_theme_color("accent", c))
            swatches.addWidget(b)
        swatches.addStretch()
        form.addRow("Accent color", swatches)
        self.body.addLayout(form)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        for i, (key, label) in enumerate(theme.EDITABLE):
            r, c = divmod(i, 2)
            cell = QHBoxLayout()
            cell.addWidget(ColorButton(getattr(theme.CURRENT, key),
                                       lambda col, k=key: self.win.set_theme_color(k, col), f"{label} color"))
            cell.addWidget(QLabel(label))
            cell.addStretch()
            grid.addLayout(cell, r, c)
        self.body.addLayout(grid)

        row = QHBoxLayout()
        row.addWidget(button("Reset colors to theme", self.win.reset_theme_colors))
        row.addStretch()
        self.body.addLayout(row)

    def _build_general(self):
        self._section("Backups & scanning")
        form = QFormLayout()
        form.setSpacing(12)
        row = QHBoxLayout()
        self.backup_dir = QLineEdit(placeholderText="Default: %LOCALAPPDATA%\\ModTender\\backups")
        self.backup_dir.editingFinished.connect(self._save)
        row.addWidget(self.backup_dir, 1)
        row.addWidget(button("Browse…", self._browse))
        form.addRow("Backup folder", row)
        self.keep = QSpinBox(minimum=1, maximum=100)
        self.keep.setFixedWidth(90)
        self.keep.valueChanged.connect(self._save)
        form.addRow("Backups to keep per game", self.keep)
        self.deep = QCheckBox("Deep check: verify every byte of every archive (slower, catches subtle damage)")
        self.deep.toggled.connect(self._save)
        form.addRow("Scanning", self.deep)
        self.body.addLayout(form)
        from ..core import paths
        info = QLabel(f"Disabled mods are parked in {paths.DATA_DIR}\\disabled so the game can't see them. "
                      "Enabling moves them back.", objectName="Muted")
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.addWidget(info)

    def _build_games(self):
        self._section("Games you added")
        self.custom = QListWidget()
        self.custom.setMaximumHeight(150)
        self.body.addWidget(self.custom)
        row = QHBoxLayout()
        row.addWidget(button("Add game", self.win.add_custom_game, icon_name="plus"))
        row.addWidget(button("Remove selected", self._remove_custom, "Danger"))
        row.addStretch()
        self.body.addLayout(row)

    def _build_updates(self):
        self._section("Updates", f"You're running ModTender {__version__}.")
        row = QHBoxLayout()
        row.addWidget(button("Check for updates", self.win.check_for_updates, "Primary", "update"))
        row.addWidget(button("Open log folder", self.win.open_log_folder, icon_name="folder",
                             tip="ModTender's log file: useful when asking for help"))
        row.addStretch()
        self.body.addLayout(row)
        self.auto_update = QCheckBox("Check for updates when ModTender starts")
        self.auto_update.toggled.connect(self._save)
        self.body.addWidget(self.auto_update)
        form = QFormLayout()
        self.repo = QLineEdit(placeholderText="owner/repository  (GitHub)")
        self.repo.setMaximumWidth(340)
        self.repo.editingFinished.connect(self._save)
        form.addRow("Release page", self.repo)
        self.body.addLayout(form)

    # --- behaviour

    def refresh(self):
        self._loading = True
        s = self.win.settings
        self.preset.setCurrentText(s.theme_preset if s.theme_preset in theme.PRESETS else "Midnight")
        self.backup_dir.setText(s.backup_dir)
        self.keep.setValue(s.keep_backups)
        self.deep.setChecked(s.deep_check)
        self.auto_update.setChecked(s.check_updates_on_start)
        self.repo.setText(s.update_repo)
        self.custom.clear()
        for g in s.custom_games:
            item = QListWidgetItem(f"{g['name']}  —  {g['path']}")
            item.setData(Qt.ItemDataRole.UserRole, g["id"])
            self.custom.addItem(item)
        self._loading = False

    def _preset_changed(self, name: str):
        if not self._loading and name != self.win.settings.theme_preset:
            self.win.set_theme_preset(name)

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
        s.check_updates_on_start = self.auto_update.isChecked()
        s.update_repo = self.repo.text().strip().strip("/")
        self.win.save_settings()

    def _remove_custom(self):
        item = self.custom.currentItem()
        if item:
            self.win.remove_custom_game(item.data(Qt.ItemDataRole.UserRole))
