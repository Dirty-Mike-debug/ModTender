"""Main window: sidebar, page stack, and every action the pages trigger."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import APP_NAME, __version__
from ..core import backups, manager
from ..core.games import Game, detect_games, make_custom_game_entry
from ..core.issues import analyze
from ..core.manager import ModActionError
from ..core.report import build_report
from ..core.settings import load_settings, save_settings
from ..core.scanner import scan_game
from .pages import BackupsPage, DashboardPage, IssuesPage, ModsPage, SettingsPage
from .widgets import Task, reveal_in_explorer

NAV = [("dashboard", "Dashboard"), ("mods", "Mods"), ("issues", "Issues"),
       ("backups", "Backups"), ("settings", "Settings")]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1240, 780)
        self.setMinimumSize(980, 620)

        self.settings = load_settings()
        self.games: list[Game] = []
        self.game: Game | None = None
        self.scan = None
        self.issues = []
        self.backups = []
        self._tasks: list[Task] = []
        self._busy = False

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

        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)

        self.reload_games()
        self.go("dashboard")

    # ------------------------------------------------------------ layout

    def _build_sidebar(self) -> QWidget:
        side = QWidget(objectName="Sidebar")
        side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        side.setFixedWidth(240)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(16, 22, 16, 16)
        lay.setSpacing(6)
        lay.addWidget(QLabel(APP_NAME, objectName="Logo"))
        lay.addWidget(QLabel("Mod manager & safety tool", objectName="LogoSub"))
        lay.addSpacing(18)
        lay.addWidget(QLabel("GAME", objectName="CardTitle"))
        self.game_box = QComboBox()
        self.game_box.currentIndexChanged.connect(self._on_game_changed)
        lay.addWidget(self.game_box)
        add = QPushButton("+ Add game")
        add.clicked.connect(self.add_custom_game)
        lay.addWidget(add)
        lay.addSpacing(18)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_buttons = {}
        for key, label in NAV:
            b = QPushButton(label, objectName="Nav")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.nav.addButton(b)
            self.nav_buttons[key] = b
            lay.addWidget(b)
        lay.addStretch()
        lay.addWidget(QLabel(f"v{__version__}", objectName="LogoSub"))
        return side

    def go(self, key: str):
        self.nav_buttons[key].setChecked(True)
        page = self.pages[key]
        page.refresh()
        self.stack.setCurrentWidget(page)

    def refresh_all(self):
        for page in self.pages.values():
            page.refresh()

    # ------------------------------------------------------------ games

    def reload_games(self, select: str | None = None):
        self.games = detect_games(self.settings.custom_games)
        wanted = select or self.settings.last_game
        self.game_box.blockSignals(True)
        self.game_box.clear()
        for g in self.games:
            self.game_box.addItem(g.name, g.id)
        idx = next((i for i, g in enumerate(self.games) if g.id == wanted), 0)
        self.game_box.blockSignals(False)
        if self.games:
            self.game_box.setCurrentIndex(idx)
            self._on_game_changed(idx)
        else:
            self.game = None
            self.refresh_all()
            self.status("No supported games found. Add one with '+ Add game'.")

    def _on_game_changed(self, idx: int):
        if idx < 0 or idx >= len(self.games):
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
        ids = {g.id for g in self.games}
        entry = make_custom_game_entry(name.strip(), folder, ids)
        self.settings.custom_games.append(entry)
        self.save_settings()
        self.reload_games(select=entry["id"])

    def remove_custom_game(self, game_id: str):
        self.settings.custom_games = [g for g in self.settings.custom_games if g["id"] != game_id]
        self.save_settings()
        self.reload_games()
        self.pages["settings"].refresh()

    # ------------------------------------------------------------ background work

    def _run(self, label: str, fn, *args, on_done=None):
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
            self.status("Something went wrong.")
            QMessageBox.critical(self, APP_NAME, message.split("\n\n")[0] + "\n\n" + message[-1500:])

        # Queued so these always run on the UI thread, never the worker thread.
        task.progress.connect(lambda p, m: (self.progress.setValue(p), self.status(m)), Qt.ConnectionType.QueuedConnection)
        task.done.connect(ok, Qt.ConnectionType.QueuedConnection)
        task.failed.connect(fail, Qt.ConnectionType.QueuedConnection)
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
