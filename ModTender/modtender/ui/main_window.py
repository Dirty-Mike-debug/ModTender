"""Main window: sidebar, page stack, and every action the pages trigger."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, UPDATE_REPO, __version__
from ..core import backups, fixer, manager, paths, self_update, updates
from ..core.games import Game, detect_games, make_custom_game_entry
from ..core.issues import analyze
from ..core.log import log, log_dir
from ..core.manager import ModActionError
from ..core.report import build_report
from ..core.scanner import scan_game
from ..core.settings import load_settings, save_settings
from . import theme
from .pages import BackupsPage, DashboardPage, IssuesPage, ModsPage, SettingsPage
from .widgets import Task, app_icon, icon, logo_pixmap, reveal_in_explorer

NAV = [("dashboard", "Dashboard"), ("mods", "Mods"), ("issues", "Issues"),
       ("backups", "Backups"), ("settings", "Settings")]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.setMinimumSize(1000, 640)

        self.settings = load_settings()
        log.info("ModTender %s started (Python %s)", __version__, sys.version.split()[0])
        self.games: list[Game] = []
        self.game: Game | None = None
        self.scan = None
        self.issues = []
        self.backups = []
        self._tasks: list[Task] = []
        self._busy = False
        self.current_page = "dashboard"

        self.progress = QProgressBar()
        self.progress.setFixedWidth(200)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)

        self.apply_theme(rebuild=False)
        self._build_ui()
        self.reload_games()
        if self.settings.check_updates_on_start and self._update_repo():
            QTimer.singleShot(1500, lambda: self.check_for_updates(quiet=True))
        QTimer.singleShot(2500, self._report_finished_update)

    # ------------------------------------------------------------ layout

    def _build_ui(self):
        """(Re)build every widget. Called again after a theme change so icons pick up new colors."""
        old = self.centralWidget()
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        self.pages = {
            "dashboard": DashboardPage(self), "mods": ModsPage(self), "issues": IssuesPage(self),
            "backups": BackupsPage(self), "settings": SettingsPage(self),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        if old is not None:
            old.deleteLater()
        self.setWindowIcon(app_icon())
        self._fill_game_box()
        self.go(self.current_page)

    def _build_sidebar(self) -> QWidget:
        side = QWidget(objectName="Sidebar")
        side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        side.setFixedWidth(236)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 20, 14, 14)
        lay.setSpacing(4)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(30))
        logo.setFixedSize(30, 30)
        logo.setScaledContents(True)
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(QLabel(APP_NAME, objectName="Brand"))
        names.addWidget(QLabel("Mod manager & safety tool", objectName="BrandSub"))
        brand.addLayout(names)
        brand.addStretch()
        lay.addLayout(brand)
        lay.addSpacing(22)

        lay.addWidget(QLabel("GAME", objectName="SideLabel"))
        self.game_box = QComboBox()
        self.game_box.currentIndexChanged.connect(self._on_game_changed)
        lay.addWidget(self.game_box)
        add = QPushButton("Add game", objectName="Ghost")
        add.setIcon(icon("plus", theme.MUTED))
        add.setIconSize(QSize(14, 14))
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(self.add_custom_game)
        lay.addWidget(add)
        lay.addSpacing(16)

        lay.addWidget(QLabel("MENU", objectName="SideLabel"))
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_buttons = {}
        for key, label in NAV:
            b = QPushButton(f"  {label}", objectName="Nav")
            b.setIcon(icon(key, theme.MUTED))
            b.setIconSize(QSize(17, 17))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.nav.addButton(b)
            self.nav_buttons[key] = b
            lay.addWidget(b)
        lay.addStretch()

        upd = QPushButton("Check for updates", objectName="Ghost")
        upd.setIcon(icon("update", theme.MUTED))
        upd.setIconSize(QSize(14, 14))
        upd.setCursor(Qt.CursorShape.PointingHandCursor)
        upd.clicked.connect(lambda: self.check_for_updates())
        lay.addWidget(upd)
        lay.addWidget(QLabel(f"   Version {__version__}", objectName="Version"))
        return side

    def go(self, key: str):
        self.current_page = key
        for k, b in self.nav_buttons.items():
            b.setChecked(k == key)
            b.setIcon(icon(k, theme.ACCENT if k == key else theme.MUTED))
        page = self.pages[key]
        page.refresh()
        self.stack.setCurrentWidget(page)

    def refresh_all(self):
        for page in self.pages.values():
            page.refresh()

    # ------------------------------------------------------------ theme

    def apply_theme(self, rebuild: bool = True):
        theme.apply(QApplication.instance(), self.settings.theme_preset, self.settings.theme_overrides)
        if rebuild:
            # Rebuild after the current click finishes: the button that was clicked gets replaced.
            QTimer.singleShot(0, self._build_ui)

    def set_theme_preset(self, name: str):
        self.settings.theme_preset = name
        self.settings.theme_overrides = {k: v for k, v in self.settings.theme_overrides.items() if k == "accent"}
        self.save_settings()
        self.apply_theme()

    def set_theme_color(self, key: str, color: str):
        self.settings.theme_overrides[key] = color
        self.save_settings()
        self.apply_theme()

    def reset_theme_colors(self):
        self.settings.theme_overrides = {}
        self.save_settings()
        self.apply_theme()

    # ------------------------------------------------------------ games

    def _fill_game_box(self):
        self.game_box.blockSignals(True)
        self.game_box.clear()
        for g in self.games:
            self.game_box.addItem(g.name, g.id)
        if self.game in self.games:
            self.game_box.setCurrentIndex(self.games.index(self.game))
        self.game_box.blockSignals(False)

    def reload_games(self, select: str | None = None):
        self.games = detect_games(self.settings.custom_games)
        log.info("Games found: %s", ", ".join(f"{g.name} [{g.mods_dir}]" for g in self.games) or "none")
        wanted = select or self.settings.last_game
        self.game = None
        self._fill_game_box()
        if self.games:
            idx = next((i for i, g in enumerate(self.games) if g.id == wanted), 0)
            self.game_box.setCurrentIndex(idx)
            self._on_game_changed(idx)
        else:
            self.scan, self.issues, self.backups = None, [], []
            self.refresh_all()
            self.status("No supported games found. Add one with 'Add game'.")

    def _on_game_changed(self, idx: int):
        if idx < 0 or idx >= len(self.games):
            return
        if self.game is self.games[idx] and self.scan is not None:
            return
        self.game = self.games[idx]
        self.scan, self.issues = None, []
        self.settings.last_game = self.game.id
        self.save_settings()
        self._load_backups()
        self.refresh_all()
        self.start_scan()

    def add_custom_game(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose the game's mods folder")
        if not folder:
            return
        name, ok = QInputDialog.getText(self, "Add game", "Name for this game:", text=Path(folder).parent.name)
        if not ok or not name.strip():
            return
        entry = make_custom_game_entry(name.strip(), folder, {g.id for g in self.games})
        self.settings.custom_games.append(entry)
        self.save_settings()
        self.reload_games(select=entry["id"])

    def remove_custom_game(self, game_id: str):
        self.settings.custom_games = [g for g in self.settings.custom_games if g["id"] != game_id]
        self.save_settings()
        self.reload_games()
        self.pages["settings"].refresh()

    # ------------------------------------------------------------ background work

    def _run(self, label: str, fn, *args, on_done=None, on_fail=None):
        if self._busy:
            self.status("Please wait for the current task to finish.")
            return
        self._busy = True
        task = Task(fn, *args, parent=self)
        self._tasks.append(task)
        self.progress.setValue(0)
        self.progress.show()
        self.status(label)

        def finish():
            self._busy = False
            self.progress.hide()
            if task in self._tasks:
                self._tasks.remove(task)

        def ok(result):
            finish()
            if on_done:
                on_done(result)

        def fail(message):
            finish()
            log.error("%s failed: %s", label.rstrip("…"), message)
            if on_fail:
                return on_fail(message)
            self.status("Something went wrong.")
            QMessageBox.critical(self, APP_NAME, message.split("\n\n")[0] + "\n\n" + message[-1500:])

        queued = Qt.ConnectionType.QueuedConnection  # always handle results on the UI thread
        task.progress.connect(lambda p, m: (self.progress.setValue(p), self.status(m)), queued)
        task.done.connect(ok, queued)
        task.failed.connect(fail, queued)
        task.start()

    def start_scan(self):
        if not self.game:
            return
        game = self.game

        def done(scan):
            if self.game is not game:
                return  # user switched games mid-scan
            self.scan = scan
            self.issues = analyze(scan)
            self.refresh_all()
            self.status(f"Scanned {len(scan.mods)} mods · {len(self.issues)} issues")

        self._run(f"Scanning {game.name}…", scan_game, game, self.settings.deep_check, on_done=done)

    # ------------------------------------------------------------ updates

    def _update_repo(self) -> str:
        return self.settings.update_repo or UPDATE_REPO

    def check_for_updates(self, quiet: bool = False):
        repo = self._update_repo()
        if not repo:
            if not quiet:
                QMessageBox.information(
                    self, "Check for updates",
                    f"You're running ModTender {__version__}.\n\n"
                    "Update checking isn't connected to a release page yet. Once ModTender has a GitHub "
                    "repository, enter it under Settings → Updates (for example yourname/ModTender).")
            return

        def done(info):
            if info.newer:
                box = QMessageBox(self)
                box.setWindowTitle("Update available")
                box.setIcon(QMessageBox.Icon.Information)
                box.setText(f"ModTender {info.latest} is available. You have {info.current}.")
                box.setInformativeText(("What's new:\n" + info.notes) if info.notes else "")
                auto = info.asset_url and self_update.can_self_update()
                install = box.addButton("Update now", QMessageBox.ButtonRole.AcceptRole) if auto else None
                page = box.addButton("View release" if auto else "Download", QMessageBox.ButtonRole.ActionRole)
                box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                if install is not None and box.clickedButton() is install:
                    self._install_update(info)
                elif box.clickedButton() is page:
                    QDesktopServices.openUrl(QUrl(info.url))
            else:
                self.status(f"ModTender is up to date ({info.current}).")
                if not quiet:
                    QMessageBox.information(self, "Check for updates",
                                            f"You're up to date. ModTender {info.current} is the latest version.")

        def fail(message):
            first = message.split("\n\n")[0]
            self.status(f"Update check failed: {first}")
            if not quiet:
                QMessageBox.warning(self, "Check for updates", first)

        self._run("Checking for updates…", updates.check_for_update, repo, on_done=done, on_fail=fail)

    def _install_update(self, info):
        def downloaded(new_root):
            QMessageBox.information(
                self, "Installing update",
                f"ModTender {info.latest} is downloaded.\n\nModTender will close, install the update and "
                "open again by itself in a few seconds. Your settings, backups and mods aren't touched."
                + ("\n\nIf Windows asks whether to allow the installer, choose Yes." if updates.is_app_build() else ""))
            try:
                self_update.launch_installer(new_root)
            except OSError as exc:
                QMessageBox.warning(self, "Installing update", f"Couldn't start the installer: {exc}")
                return
            self.save_settings()
            QApplication.instance().quit()

        def failed(message):
            QMessageBox.warning(self, "Update", message.split("\n\n")[0])

        self._run(f"Downloading ModTender {info.latest}…", self_update.download_update, info,
                  on_done=downloaded, on_fail=failed)

    def _report_finished_update(self):
        previous, self.settings.last_version = self.settings.last_version, __version__
        self.save_settings()
        text = self_update.pop_update_log()
        if text:
            log.info("Last update log:\n%s", text.strip())
        if "UPDATE FAILED" in text:
            QMessageBox.warning(self, "Update",
                                "The last update couldn't be installed, so ModTender kept the previous version. "
                                "Details:\n\n" + text[-1200:])
        elif previous and previous != __version__:
            self.status(f"Updated to ModTender {__version__}.")
            QMessageBox.information(self, "Update", f"ModTender was updated from {previous} to {__version__}.")

    # ------------------------------------------------------------ fixes

    def fix_issue(self, issue):
        if not self.game or not issue.fixable:
            return
        if issue.action == "search":
            QDesktopServices.openUrl(QUrl(issue.params["url"]))
            return
        answer = QMessageBox.question(self, "Fix issue", f"{issue.title}\n\nModTender will: {issue.action_label}.\n\n"
                                      "Nothing is deleted. Continue?")
        if answer == QMessageBox.StandardButton.Yes:
            self._apply_fixes([issue], backup=False)

    def fix_all(self):
        if not self.game:
            return
        todo = [i for i in self.issues if i.fixable and i.safe]
        if not todo:
            QMessageBox.information(self, "Fix all", "There's nothing ModTender can fix automatically right now.")
            return
        manual = sum(1 for i in self.issues if not (i.fixable and i.safe))
        lines = "\n".join(f"•  {i.action_label}" for i in todo[:12]) + (f"\n•  …and {len(todo) - 12} more" if len(todo) > 12 else "")
        box = QMessageBox(self)
        box.setWindowTitle("Fix all")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"ModTender will apply {len(todo)} fix(es):")
        box.setInformativeText(lines + "\n\nNothing is deleted: removed files go to the disabled or quarantine folder."
                               + (f"\n\n{manual} issue(s) need you to decide, so they're left alone." if manual else "")
                               + "\n\nClose the game before continuing.")
        check = QCheckBox("Back up my mods first (recommended)")
        check.setChecked(self.settings.backup_before_fix)
        box.setCheckBox(check)
        go = box.addButton("Fix all", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not go:
            return
        self.settings.backup_before_fix = check.isChecked()
        self.save_settings()
        self._apply_fixes(todo, backup=check.isChecked())

    def _apply_fixes(self, issues, backup: bool):
        game = self.game
        root = self.settings.backup_root if backup else None

        def done(result):
            self._load_backups()
            self.scan = None
            self.start_scan()
            msg = "\n".join(f"✓  {d}" for d in result.done[:20]) or "Nothing needed changing."
            if len(result.done) > 20:
                msg += f"\n…and {len(result.done) - 20} more"
            if result.skipped:
                msg += "\n\nCouldn't fix:\n" + "\n".join(f"✗  {s}" for s in result.skipped)
            if result.backup:
                msg += f"\n\nBackup saved first: {result.backup.name}"
            QMessageBox.information(self, "Fixes applied", msg)

        self._run("Fixing…", fixer.fix_issues, game, issues, root, on_done=done)

    def open_log_folder(self):
        reveal_in_explorer(log_dir())

    def open_quarantine_folder(self):
        if self.game:
            reveal_in_explorer(paths.quarantine_dir(self.game.id))

    # ------------------------------------------------------------ mod actions

    def set_enabled(self, mods, enable: bool):
        if not mods or not self.game:
            return
        errors, changed = [], 0
        for m in mods:
            if m.enabled == enable:
                continue
            try:
                (manager.enable_mod if enable else manager.disable_mod)(self.game, m)
                changed += 1
            except (ModActionError, OSError) as exc:
                errors.append(f"{m.name}: {exc}")
        if errors:
            QMessageBox.warning(self, APP_NAME, "Some mods couldn't be changed:\n\n" + "\n".join(errors))
        if changed:
            self.status(f"{'Enabled' if enable else 'Disabled'} {changed} mod(s).")
            self.start_scan()

    def reveal(self, path):
        reveal_in_explorer(Path(path))

    def open_mods_folder(self):
        if self.game:
            self.game.mods_dir.mkdir(parents=True, exist_ok=True)
            reveal_in_explorer(self.game.mods_dir)

    def export_report(self):
        if not self.scan:
            QMessageBox.information(self, APP_NAME, "Scan the game first.")
            return
        default = str(Path.home() / "Desktop" / f"ModTender report - {self.game.name}.txt")
        target, _ = QFileDialog.getSaveFileName(self, "Save report", default, "Text files (*.txt)")
        if target:
            Path(target).write_text(build_report(self.scan, self.issues), encoding="utf-8")
            self.status(f"Report saved to {target}")
            reveal_in_explorer(Path(target))

    # ------------------------------------------------------------ backups

    def _load_backups(self):
        self.backups = backups.list_backups(self.game, self.settings.backup_root) if self.game else []

    def create_backup(self):
        if not self.game:
            return
        game, root, keep = self.game, self.settings.backup_root, self.settings.keep_backups

        def work(progress=None):
            b = backups.create_backup(game, root, progress=progress)
            backups.prune_backups(game, root, keep)
            return b

        def done(b):
            self._load_backups()
            self.refresh_all()
            self.status(f"Backup saved: {b.path.name}")

        self._run(f"Backing up {game.name}…", work, on_done=done)

    def restore_backup(self, backup):
        answer = QMessageBox.question(
            self, "Restore backup",
            f"Restore the backup from {backup.created:%Y-%m-%d %H:%M}?\n\n"
            "Your current mods folder won't be deleted. It's renamed to 'mods.before-restore-…' "
            "so you can go back to it.\n\nClose the game before restoring.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def done(kept):
            self.status(f"Restored. Previous mods kept in {kept}")
            self.scan = None
            self.start_scan()

        self._run("Restoring backup…", backups.restore_backup, self.game, backup, on_done=done)

    def delete_backup(self, backup):
        answer = QMessageBox.question(self, "Delete backup",
                                      f"Permanently delete the backup from {backup.created:%Y-%m-%d %H:%M}?")
        if answer == QMessageBox.StandardButton.Yes:
            try:
                backup.path.unlink()
            except OSError as exc:
                QMessageBox.warning(self, APP_NAME, f"Couldn't delete it: {exc}")
            self._load_backups()
            self.refresh_all()

    def open_backup_folder(self):
        if self.game:
            folder = self.settings.backup_root / self.game.id
            folder.mkdir(parents=True, exist_ok=True)
            reveal_in_explorer(folder)

    # ------------------------------------------------------------ misc

    def save_settings(self):
        try:
            save_settings(self.settings)
        except OSError as exc:
            self.status(f"Couldn't save settings: {exc}")

    def status(self, text: str):
        self.statusBar().showMessage(text)

    def closeEvent(self, event):
        if self._busy:
            answer = QMessageBox.question(self, APP_NAME, "A task is still running. Quit anyway?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
