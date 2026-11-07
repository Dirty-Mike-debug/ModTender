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
from ..core import backups, fixer, manager, paths, self_update, sources, updates, workshop_names
from ..core.games import Game, detect_games, make_custom_game_entry
from ..core.issues import analyze
from ..core.log import log, log_dir
from ..core.manager import ModActionError
from ..core.report import build_report, human_size
from ..core.scanner import scan_game
from ..core.settings import load_settings, save_settings
from . import theme
from .pages import BackupsPage, DashboardPage, IssuesPage, ModsPage, SettingsPage, SourcesPage
from .widgets import Task, app_icon, icon, logo_pixmap, reveal_in_explorer

NAV = [("dashboard", "Dashboard"), ("mods", "Mods"), ("issues", "Issues"),
       ("backups", "Backups"), ("sources", "Get mods"), ("settings", "Settings")]


class MainWindow(QMainWindow):
    def __init__(self, user=None):
        super().__init__()
        self.user = user
        self.switch_requested = False
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.setMinimumSize(1000, 640)

        self.setAcceptDrops(True)  # drop downloaded mods anywhere on the window to install them
        self.settings = load_settings()
        log.info("ModTender %s started (Python %s), user: %s", __version__, sys.version.split()[0],
                 user.name if user else "-")
        self.games: list[Game] = []
        self.game: Game | None = None
        self.scan = None
        self.issues = []
        self.backups = []
        self._tasks: list[Task] = []
        self._busy = False
        self.current_page = "dashboard"  # replaced by the user's start page below
        self.mod_sources = sources.load_sources()

        self.progress = QProgressBar()
        self.progress.setFixedWidth(200)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)

        if self.settings.start_page in dict(NAV):
            self.current_page = self.settings.start_page
        self.apply_theme(rebuild=False)
        self._build_ui()
        self.reload_games()
        if self.settings.check_updates_on_start and self._update_repo():
            QTimer.singleShot(1500, lambda: self.check_for_updates(quiet=True))
        QTimer.singleShot(2500, self._report_finished_update)
        QTimer.singleShot(4000, self._refresh_sources)
        QTimer.singleShot(5000, self._fetch_steam_names)
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._auto_backup_tick)
        self._auto_timer.start(15 * 60 * 1000)

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
            "backups": BackupsPage(self), "sources": SourcesPage(self), "settings": SettingsPage(self),
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
        side.setFixedWidth(260)
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
        game_row = QHBoxLayout()
        game_row.setSpacing(6)
        game_row.addWidget(self.game_box, 1)
        self.star = QPushButton("☆", objectName="Star")
        self.star.setFixedSize(34, 30)
        self.star.setToolTip("Pin this game to the top of the list")
        self.star.setCursor(Qt.CursorShape.PointingHandCursor)
        self.star.clicked.connect(self.toggle_favorite)
        game_row.addWidget(self.star)
        lay.addLayout(game_row)
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

        if self.user is not None:
            from .signin import avatar
            who = QPushButton(f"  {self.user.name}", objectName="Ghost")
            who.setIcon(QIcon(avatar(self.user, 12)))
            who.setIconSize(QSize(22, 22))
            who.setToolTip("Switch user")
            who.setCursor(Qt.CursorShape.PointingHandCursor)
            who.clicked.connect(self.switch_user)
            lay.addWidget(who)
        upd = QPushButton("Check for updates", objectName="Ghost")
        upd.setIcon(icon("update", theme.MUTED))
        upd.setIconSize(QSize(14, 14))
        upd.setCursor(Qt.CursorShape.PointingHandCursor)
        upd.clicked.connect(lambda: self.check_for_updates())
        lay.addWidget(upd)
        bug = QPushButton("Report a problem", objectName="Ghost")
        bug.setIcon(icon("crash", theme.MUTED))
        bug.setIconSize(QSize(14, 14))
        bug.setCursor(Qt.CursorShape.PointingHandCursor)
        bug.clicked.connect(lambda: self.report_problem())
        lay.addWidget(bug)
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
        theme.apply(QApplication.instance(), self.settings.theme_preset, self.settings.theme_overrides,
                    self.settings.text_scale, self.settings.compact)
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

    def _sort_games(self):
        favs = self.settings.favorite_games
        self.games.sort(key=lambda g: (g.id not in favs, favs.index(g.id) if g.id in favs else 0))

    def _update_star(self):
        fav = bool(self.game and self.game.id in self.settings.favorite_games)
        self.star.setText("★" if fav else "☆")
        self.star.setStyleSheet(f"color: {theme.WARNING};" if fav else "")
        self.star.setToolTip("Unpin this game" if fav else "Pin this game to the top of the list")

    def toggle_favorite(self):
        if not self.game:
            return
        favs = self.settings.favorite_games
        if self.game.id in favs:
            favs.remove(self.game.id)
        else:
            favs.append(self.game.id)
        self.save_settings()
        self._sort_games()
        self._fill_game_box()

    def _fill_game_box(self):
        self.game_box.blockSignals(True)
        self.game_box.clear()
        for g in self.games:
            self.game_box.addItem(("★  " if g.id in self.settings.favorite_games else "") + g.name, g.id)
        if self.game in self.games:
            self.game_box.setCurrentIndex(self.games.index(self.game))
        self.game_box.view().setMinimumWidth(max(self.game_box.view().sizeHintForColumn(0) + 30, 220))
        self.game_box.setToolTip(self.game.name if self.game else "")
        self.game_box.blockSignals(False)
        self._update_star()

    def reload_games(self, select: str | None = None):
        self.games = detect_games(self.settings.custom_games)
        self._sort_games()
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
        self.game_box.setToolTip(self.game.name)
        self._update_star()
        self.scan, self.issues = None, []
        self.settings.last_game = self.game.id
        self.save_settings()
        self._load_backups()
        self.refresh_all()
        self.start_scan()
        QTimer.singleShot(400, self._offer_resume_hunt)

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
            self._changes_cache = {}
            QTimer.singleShot(3000, self._auto_backup_tick)
            untitled = [m.workshop_id for m in scan.mods if m.workshop and not m.title]
            if untitled:
                self._fetch_workshop_titles(scan, untitled)

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
        if issue.action in ("search", "open_url"):
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

    def _refresh_sources(self):
        """Fetch the latest 'Get mods' list in the background (never blocks other tasks)."""
        task = Task(sources.refresh_sources, self._update_repo(), parent=self)
        self._tasks.append(task)

        def done(data):
            self.mod_sources = data
            if task in self._tasks:
                self._tasks.remove(task)
            if self.current_page == "sources":
                self.pages["sources"].refresh()

        task.done.connect(done, Qt.ConnectionType.QueuedConnection)
        task.failed.connect(lambda _m: self._tasks.remove(task) if task in self._tasks else None,
                            Qt.ConnectionType.QueuedConnection)
        task.start()

    def _fetch_workshop_titles(self, scan, ids):
        """Look up Workshop item names in the background, then show them."""
        task = Task(workshop_names.fetch_titles, ids, parent=self)
        self._tasks.append(task)

        def done(cache):
            if task in self._tasks:
                self._tasks.remove(task)
            if self.scan is scan and workshop_names.apply_titles(scan.mods, cache) < len(ids):
                self.issues = analyze(scan)
                self.refresh_all()

        task.done.connect(done, Qt.ConnectionType.QueuedConnection)
        task.failed.connect(lambda _m: self._tasks.remove(task) if task in self._tasks else None,
                            Qt.ConnectionType.QueuedConnection)
        task.start()

    def _fetch_steam_names(self):
        from ..core import steam_names
        unknown = [g.steam_appid for g in self.games if g.name.startswith("Steam app ")]
        if not unknown:
            return
        task = Task(steam_names.fetch_names, unknown, parent=self)
        self._tasks.append(task)

        def done(names):
            if task in self._tasks:
                self._tasks.remove(task)
            changed = False
            for g in self.games:
                n = names.get(str(g.steam_appid))
                if g.name.startswith("Steam app ") and n:
                    g.name = f"{n} (Steam Workshop)"
                    changed = True
            if changed:
                self._fill_game_box()
                self.refresh_all()

        task.done.connect(done, Qt.ConnectionType.QueuedConnection)
        task.failed.connect(lambda _m: self._tasks.remove(task) if task in self._tasks else None,
                            Qt.ConnectionType.QueuedConnection)
        task.start()

    def bring_to_front(self):
        self.showNormal() if self.isMinimized() else self.show()
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except Exception:
                pass

    def open_url(self, url: str):
        QDesktopServices.openUrl(QUrl(url))

    # ------------------------------------------------------------ users

    def switch_user(self):
        if self._busy:
            self.status("Please wait for the current task to finish.")
            return
        self.save_settings()
        self.switch_requested = True
        self.close()

    def edit_name(self):
        from ..core import users
        name, ok = QInputDialog.getText(self, "Your name", "Name:", text=self.user.name)
        if ok and name.strip():
            self.user.name = name.strip()[:40]
            users.update_user(self.user)
            self.apply_theme()  # rebuild so the sidebar shows the new name

    def choose_avatar(self):
        from PySide6.QtGui import QImage
        from ..core import users
        path, _ = QFileDialog.getOpenFileName(self, "Choose a picture", str(Path.home() / "Pictures"),
                                              "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Picture", "That file couldn't be opened as a picture.")
            return
        side = min(img.width(), img.height())  # crop to a centered square, keep it small
        img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side).scaled(
            256, 256, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        img.save(str(users.user_dir(self.user.id) / "avatar.png"), "PNG")
        self.user.avatar = "avatar.png"
        users.update_user(self.user)
        self.apply_theme()

    def remove_avatar(self):
        from ..core import users
        if self.user.avatar_path:
            self.user.avatar_path.unlink(missing_ok=True)
        self.user.avatar = ""
        users.update_user(self.user)
        self.apply_theme()

    def set_avatar_color(self, color: str):
        from ..core import users
        self.user.color = color
        users.update_user(self.user)
        self.apply_theme()

    def edit_pin(self):
        from .signin import PinDialog
        if PinDialog(self.user, self).exec():
            self.status("PIN saved." if self.user.has_pin else "PIN removed.")
            self.pages["settings"].refresh()

    def add_user(self):
        from .signin import NewUserDialog
        dlg = NewUserDialog(self)
        if dlg.exec() and dlg.user:
            QMessageBox.information(self, "Add user", f"Added {dlg.user.name}. Use Switch user to sign in as them.")
            self.pages["settings"].refresh()

    def delete_me(self):
        from ..core import users
        from .signin import confirm_delete
        if len(users.list_users()) < 2:
            QMessageBox.information(self, "Delete user", "You're the only user, so this user can't be deleted.")
            return
        if confirm_delete(self, self.user):
            users.delete_user(self.user)
            self.switch_requested = True
            self.close()

    def set_show_signin(self, value: bool):
        from ..core import users
        users.set_show_signin(value)

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

    # ------------------------------------------------------------ find the broken mod

    def show_error(self, title: str, detail) -> None:
        log.error("%s: %s", title, detail)
        QMessageBox.warning(self, APP_NAME, f"{title}.\n\n{detail}")

    def find_broken_mod(self):
        from ..core import bisect
        from .hunt_dialog import HuntDialog, unsupported_reason
        if not self.game:
            return
        hunt = bisect.load(self.game.id)
        if hunt is None:
            why = unsupported_reason(self.game)
            if why:
                QMessageBox.information(self, "Find the broken mod", why)
                return
            if not self.scan:
                QMessageBox.information(self, APP_NAME, "Scan the game first.")
                return
            on = [m for m in self.scan.mods if m.enabled and not m.workshop and not m.protected]
            import math
            rounds = 2 + math.ceil(math.log2(max(2, len(on))))
            answer = QMessageBox.question(
                self, "Find the broken mod",
                f"ModTender will help you find which of your {len(on)} mods is causing a crash or bug.\n\n"
                f"Each round it turns some mods off, you start the game and say whether the problem still "
                f"happens. It takes about {rounds} rounds. Mods that other mods need are handled for you, and "
                "at the end everything is put back the way it was.\n\n"
                "Don't save your game during the search. Start now?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                hunt = bisect.start(self.game, self.scan.mods)
            except Exception as exc:
                self.show_error("Couldn't start the search", exc)
                return
            finally:
                QApplication.restoreOverrideCursor()
        dlg = HuntDialog(self, self.game, hunt)
        dlg.exec()
        self.scan = None
        self.start_scan()

    def _offer_resume_hunt(self):
        from ..core import bisect
        if not self.game or bisect.load(self.game.id) is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Find the broken mod")
        box.setText(f"You're in the middle of finding a broken mod in {self.game.name}. Some mods are turned "
                    "off for it right now.")
        carry = box.addButton("Carry on", QMessageBox.ButtonRole.AcceptRole)
        stop = box.addButton("Stop and put everything back", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is carry:
            self.find_broken_mod()
        elif box.clickedButton() is stop:
            problems = bisect.stop(self.game)
            if problems:
                self.show_error("Some mods couldn't be put back", "\n".join(problems))
            self.scan = None
            self.start_scan()

    # ------------------------------------------------------------ sharing and matching mod lists

    def share_mod_list(self):
        from ..core import modlist
        from ..core.paths import desktop_dir
        if not self.game or not self.scan:
            QMessageBox.information(self, APP_NAME, "Scan the game first.")
            return
        safe = "".join(ch for ch in self.game.name if ch not in '\\/:*?"<>|').strip()
        default = str(desktop_dir() / f"{safe} mods.modtender")
        target, _ = QFileDialog.getSaveFileName(self, "Save your mod list", default, "ModTender mod list (*.modtender)")
        if not target:
            return
        modlist.export_setup(self.game, self.scan.mods, Path(target))
        on = sum(m.enabled for m in self.scan.mods)
        self.status(f"Saved a list of {on} mods to {target}")
        reveal_in_explorer(Path(target))
        QMessageBox.information(self, "Share my mod list",
                                f"Saved a list of your {on} turned-on mods.\n\nSend this file to a friend. In "
                                "ModTender they choose Match mods, open the file, and see exactly what they're "
                                "missing or have a different version of.")

    def compare_mod_list(self):
        from .compare_dialog import CompareDialog
        if not self.game or not self.scan:
            QMessageBox.information(self, APP_NAME, "Scan the game first.")
            return
        dlg = CompareDialog(self, self.game, list(self.scan.mods))
        dlg.exec()
        if dlg.changed:
            self.scan = None
            self.start_scan()

    # ------------------------------------------------------------ installing mods

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        files = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if files:
            event.acceptProposedAction()
            self.install_mods(files)

    def choose_mods_to_install(self):
        if not self.game:
            return
        start = str(Path.home() / "Downloads")
        files, _ = QFileDialog.getOpenFileNames(self, f"Choose mods to install into {self.game.name}", start,
                                                "Mods (*.zip *.jar *.pak *.package *.archive *.esp *.esm *.esl "
                                                "*.dll *.rar *.7z *.ts4script);;All files (*)")
        if files:
            self.install_mods([Path(f) for f in files])

    def install_mods(self, files):
        if not self.game:
            QMessageBox.information(self, APP_NAME, "Pick a game first.")
            return
        names = "\n".join(f"   {f.name}" for f in files[:12]) + (f"\n   …and {len(files) - 12} more" if len(files) > 12 else "")
        answer = QMessageBox.question(
            self, "Install mods",
            f"Install {'this file' if len(files) == 1 else f'these {len(files)} files'} into {self.game.name}?\n\n"
            f"{names}\n\nIf a mod with the same name is already installed, the old copy is moved to "
            "ModTender's quarantine folder, not deleted.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        from ..core import installer
        game = self.game

        def work(progress):
            progress(30, f"Installing into {game.name}…")
            return installer.install(game, files)

        def done(result):
            lines = []
            if result.installed:
                lines.append("Installed:\n" + "\n".join(f"   {n}" for n in result.installed))
            if result.replaced:
                lines.append("Older copies moved to quarantine:\n" + "\n".join(f"   {n}" for n in result.replaced))
            if result.problems:
                lines.append("Not installed:\n" + "\n".join(f"   {n}" for n in result.problems))
            box = QMessageBox.warning if result.problems and not result.installed else QMessageBox.information
            box(self, "Install mods", "\n\n".join(lines) or "Nothing was installed.")
            if result.installed:
                self.status(f"Installed {len(result.installed)} item(s). Scanning for issues…")
                self.scan = None
                self.start_scan()

        self._run("Installing mods…", work, on_done=done)

    # ------------------------------------------------------------ mod updates (Modrinth)

    def check_mod_updates(self):
        if not self.game or not self.scan:
            QMessageBox.information(self, APP_NAME, "Scan the game first.")
            return
        from ..core import modupdates
        game, mods = self.game, list(self.scan.mods)

        def failed(message):
            QMessageBox.warning(self, "Mod updates", message.split("\n\n")[0])

        def found(result):
            from .mod_updates import ModUpdatesDialog
            self.status(f"{len(result.updates)} mod update(s) found.")
            dlg = ModUpdatesDialog(self, game, result)
            if dlg.exec() and dlg.chosen:
                self._install_mod_updates(game, dlg.chosen)

        def work(progress):
            try:
                return modupdates.check_updates(game, mods, progress)
            except modupdates.UpdateCheckError as exc:
                raise RuntimeError(str(exc)) from None

        self._run("Checking Modrinth for mod updates…", work, on_done=found, on_fail=failed)

    def _install_mod_updates(self, game, chosen):
        from ..core import modupdates

        def done(result):
            ok, problems = result
            parts = []
            if ok:
                parts.append(f"Updated {len(ok)} mod(s):\n" + "\n".join(f"   {l}" for l in ok[:30]))
            if problems:
                parts.append("Couldn't update:\n" + "\n".join(f"   {l}" for l in problems[:30]))
            QMessageBox.information(self, "Mod updates", "\n\n".join(parts) or "Nothing changed.")
            self.scan = None
            self.start_scan()

        self._run(f"Updating {len(chosen)} mod(s)…", lambda progress: modupdates.apply_updates(game, chosen, progress),
                  on_done=done)

    def reveal(self, path):
        reveal_in_explorer(Path(path))

    def open_mods_folder(self):
        if self.game:
            self.game.mods_dir.mkdir(parents=True, exist_ok=True)
            reveal_in_explorer(self.game.mods_dir)

    def report_problem(self):
        from ..core import problem_report
        text, ok = QInputDialog.getMultiLineText(
            self, "Report a problem",
            "What went wrong? What were you doing when it happened?\n\n"
            "ModTender will save a zip with this description, its log, your mod list and some system info. "
            "These include folder paths on your PC (with your Windows user name). Nothing is sent "
            "automatically: you choose whether to share it.")
        if not ok:
            return
        try:
            target = problem_report.build_bundle(problem_report.default_path(), text, self.games, self.game,
                                                 self.scan, self.issues)
        except OSError as exc:
            QMessageBox.warning(self, "Report a problem", f"Couldn't save the report: {exc}")
            return
        reveal_in_explorer(target)
        box = QMessageBox(self)
        box.setWindowTitle("Report a problem")
        box.setText(f"Saved {target.name} to {target.parent}.")
        box.setInformativeText("To send it to the developer, open a report on GitHub and drag the zip into it "
                               "(you'll need a free GitHub account). Or send the zip directly to whoever "
                               "gave you ModTender.")
        github = box.addButton("Open GitHub report page", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Done", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is github:
            QDesktopServices.openUrl(QUrl(problem_report.issue_url(text, self.game)))

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
        self._changes_cache = {}

    def changes_since(self, backup):
        """What changed between a backup and the current scan (cached; None before a scan)."""
        if self.scan is None or backup is None:
            return None
        key = (str(backup.path), id(self.scan))
        cache = getattr(self, "_changes_cache", {})
        if key not in cache:
            try:
                cache[key] = backups.changes_since(backup, self.scan)
            except Exception as exc:
                log.warning("Couldn't compare with %s: %s", backup.path.name, exc)
                cache[key] = None
            self._changes_cache = cache
        return cache[key]

    def backup_storage(self) -> int:
        try:
            return backups.storage_used(self.game, self.settings.backup_root) if self.game else 0
        except OSError:
            return 0

    def read_crash_log(self):
        from ..core import crashlogs
        if not self.game:
            return
        mods = self.scan.mods if self.scan else []
        logs = crashlogs.find_logs(self.game)
        start = str(logs[0]) if logs else str(self.game.mods_dir.parent)
        path, _ = QFileDialog.getOpenFileName(self, "Open a crash report or log", start,
                                              "Logs and crash reports (*.txt *.log);;All files (*)")
        if not path:
            return
        report = crashlogs.analyze_log(Path(path), mods)
        if report is None:
            QMessageBox.warning(self, "Read crash log", "That file couldn't be opened.")
            return
        log.info("[%s] Read crash log %s: %d suspect(s)", self.game.id, path, len(report.suspects))
        box = QMessageBox(self)
        box.setWindowTitle("Crash log")
        box.setText(crashlogs.describe(report))
        top = next((s for s in report.suspects if s.mod_file), None)
        if top:
            box.setInformativeText(f"To test it, turn off {top.name} and start the game again. If the problem "
                                   "goes away, update or replace that mod.")
        if report.excerpt:
            box.setDetailedText(report.excerpt)
        off = box.addButton(f"Turn off {top.name}", QMessageBox.ButtonRole.AcceptRole) if top else None
        opened = box.addButton("Open the log", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if off is not None and box.clickedButton() is off:
            from ..core.issues import Issue
            self._apply_fixes([Issue("warning", "Crash suspect", "", "", [top.mod_file], action="disable",
                                     params={"mods": [top.mod_file]}, action_label=f"Turn off {top.name}")],
                              backup=False)
        elif box.clickedButton() is opened:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def show_changes(self, backup):
        ch = self.changes_since(backup)
        if ch is None:
            QMessageBox.information(self, "What changed", "Scan the game first.")
            return
        if not ch.count:
            QMessageBox.information(self, "What changed",
                                    f"Nothing changed since the backup from {backup.created:%b %d, %H:%M}.")
            return
        lines = []
        for label, items in (("Added", ch.added), ("Removed", ch.removed), ("Updated", ch.updated),
                             ("Turned on", ch.enabled), ("Turned off", ch.disabled)):
            if items:
                lines.append(f"{label} ({len(items)}):\n" + "\n".join(f"   {n}" for n in items[:25])
                             + (f"\n   …and {len(items) - 25} more" if len(items) > 25 else ""))
        box = QMessageBox(self)
        box.setWindowTitle("What changed")
        box.setText(f"Since the backup from {backup.created:%b %d, %H:%M}: {ch.summary()}.")
        box.setInformativeText("If the game started crashing after these changes, restore this backup "
                               "to put everything back.")
        box.setDetailedText("\n\n".join(lines))
        restore = box.addButton("Restore this backup", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is restore:
            self.restore_backup(backup)

    def mark_working(self, backup, pinned: bool):
        backups.set_pinned(self.game, self.settings.backup_root, backup, pinned)
        self.status("Marked as a working setup. It won't be deleted automatically." if pinned
                    else "No longer marked as working.")
        self._load_backups()
        self.refresh_all()

    def roll_back(self):
        working = backups.last_working(self.backups)
        if working is None:
            QMessageBox.information(self, "Roll back", "Mark a backup as working first: pick a backup from a time "
                                    "the game ran fine and click Mark as working.")
            return
        self.restore_backup(working)

    def set_auto_backup(self, every: str, on_change: bool):
        if not self.game:
            return
        if every == "off" and not on_change:
            self.settings.auto_backups.pop(self.game.id, None)
        else:
            self.settings.auto_backups[self.game.id] = {"every": every, "on_change": on_change}
        self.save_settings()
        QTimer.singleShot(1000, self._auto_backup_tick)

    def _auto_backup_tick(self):
        """Run at most one due automatic backup. Called on a timer and after scans."""
        if self._busy:
            return
        root, keep = self.settings.backup_root, self.settings.keep_backups
        # The current game first: it may also need an "after a change" backup.
        if self.game and self.scan is not None and self.game.id in self.settings.auto_backups:
            cfg = self.settings.auto_backups[self.game.id]
            note = None
            if backups.is_due(self.backups, cfg.get("every", "off")):
                note = "Scheduled"
            elif cfg.get("on_change"):
                latest = self.backups[0] if self.backups else None
                ch = self.changes_since(latest) if latest else None
                if latest is None or (ch is not None and ch.count):
                    note = "Mods changed"
            if note and not self.game.workshop_only:
                return self.create_backup(note=note, quiet=True)
        for g in self.games:
            cfg = self.settings.auto_backups.get(g.id)
            if not cfg or g is self.game or g.workshop_only or not g.mods_dir.is_dir():
                continue
            if backups.is_due(backups.list_backups(g, root), cfg.get("every", "off")):
                def work(progress=None, g=g):
                    b = backups.create_backup(g, root, note="Scheduled", progress=progress)
                    backups.prune_backups(g, root, keep)
                    return b
                return self._run(f"Automatic backup of {g.name}…", work,
                                 on_done=lambda b, g=g: self.status(f"Automatic backup of {g.name} saved."),
                                 on_fail=lambda m, g=g: self.status(f"Automatic backup of {g.name} failed: "
                                                                    + m.split(chr(10))[0]))

    def create_backup(self, note: str = "Manual", quiet: bool = False):
        if not self.game:
            return
        if self.game.workshop_only:
            QMessageBox.information(self, "Back up", "All of this game's mods come from the Steam Workshop. Steam keeps "
                                    "them, so there's nothing to back up. Resubscribe on Steam to get any of them back.")
            return
        game, root, keep = self.game, self.settings.backup_root, self.settings.keep_backups

        def work(progress=None):
            b = backups.create_backup(game, root, note=note, progress=progress)
            backups.prune_backups(game, root, keep)
            return b

        def done(b):
            if self.game is game:
                self._load_backups()
                self.refresh_all()
            self.status(f"{'Automatic backup' if quiet else 'Backup'} saved: {human_size(b.new_bytes)} of new space used.")

        def fail(message):
            first = message.split("\n\n")[0]
            self.status(f"Backup failed: {first}")
            if not quiet:
                QMessageBox.warning(self, "Back up", first)

        self._run(f"{'Automatic backup' if quiet else 'Backing up'}: {game.name}…", work, on_done=done, on_fail=fail)

    def restore_backup(self, backup):
        ch = self.changes_since(backup)
        answer = QMessageBox.question(
            self, "Restore backup",
            f"Restore the backup from {backup.created:%Y-%m-%d %H:%M}?\n\n"
            + (f"This undoes: {ch.summary()}.\n\n" if ch and ch.count else "")
            + 
            "Your current mods folder won't be deleted. It's renamed to 'mods.before-restore-…' "
            "so you can go back to it.\n\nClose the game before restoring.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        root = self.settings.backup_root

        def done(kept):
            self.status(f"Restored. Previous mods kept in {kept}")
            self.scan = None
            self.start_scan()

        def fail(message):
            QMessageBox.warning(self, "Restore", message.split("\n\n")[0])

        self._run("Restoring backup…", lambda progress=None: backups.restore_backup(self.game, backup, progress, root),
                  on_done=done, on_fail=fail)

    def delete_backup(self, backup):
        answer = QMessageBox.question(self, "Delete backup",
                                      f"Permanently delete the backup from {backup.created:%Y-%m-%d %H:%M}?")
        if answer == QMessageBox.StandardButton.Yes:
            try:
                backups.delete_backup(self.game, self.settings.backup_root, backup)
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
        if self._busy and not self.switch_requested:
            answer = QMessageBox.question(self, APP_NAME, "A task is still running. Quit anyway?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
