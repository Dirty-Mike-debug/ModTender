"""Sign-in screen and account dialogs for local users."""
from __future__ import annotations

import time

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from ..core import users
from . import theme
from .widgets import app_icon, logo_pixmap


def avatar(user: users.User, size: int = 64) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(user.color or theme.ACCENT))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(0, 0, size * 2, size * 2))
    c = QColor(user.color or theme.ACCENT)
    p.setPen(QColor("#0b1410" if c.lightness() > 150 else "#ffffff"))
    f = QFont()
    f.setPixelSize(int(size * 0.9))
    f.setWeight(QFont.Weight.DemiBold)
    p.setFont(f)
    p.drawText(QRectF(0, 0, size * 2, size * 2), Qt.AlignmentFlag.AlignCenter, (user.name[:1] or "?").upper())
    p.end()
    return pm


def _pin_field(placeholder: str = "PIN") -> QLineEdit:
    e = QLineEdit(placeholderText=placeholder)
    e.setEchoMode(QLineEdit.EchoMode.Password)
    e.setMaxLength(32)
    return e


class NewUserDialog(QDialog):
    """Create a user: name plus an optional PIN."""

    def __init__(self, parent=None, title="Add user"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(380)
        self.user = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(QLabel(title, objectName="PageTitle"))
        hint = QLabel("A PIN is optional. It stops others on this PC opening your profile by accident.", objectName="Muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        form = QFormLayout()
        form.setSpacing(10)
        self.name = QLineEdit(placeholderText="Your name")
        self.name.setMaxLength(40)
        self.pin = _pin_field("Optional")
        self.pin2 = _pin_field("Type it again")
        form.addRow("Name", self.name)
        form.addRow("PIN", self.pin)
        form.addRow("Confirm PIN", self.pin2)
        lay.addLayout(form)
        self.error = QLabel("", objectName="Muted")
        self.error.setStyleSheet(f"color: {theme.CRITICAL};")
        lay.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Create", objectName="Primary")
        ok.setDefault(True)
        ok.clicked.connect(self._create)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def _create(self):
        name = self.name.text().strip()
        if not name:
            self.error.setText("Enter a name.")
            return
        if any(u.name.lower() == name.lower() for u in users.list_users()):
            self.error.setText("There's already a user with that name.")
            return
        if self.pin.text() != self.pin2.text():
            self.error.setText("The two PINs don't match.")
            return
        if self.pin.text() and len(self.pin.text()) < 4:
            self.error.setText("Use at least 4 characters for the PIN.")
            return
        self.user = users.create_user(name, self.pin.text())
        self.accept()


class PinDialog(QDialog):
    """Change or remove the PIN of a user (asks for the current one first)."""

    def __init__(self, user: users.User, parent=None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("PIN")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(QLabel("Change PIN" if user.has_pin else "Set a PIN", objectName="PageTitle"))
        form = QFormLayout()
        self.current = _pin_field("Current PIN")
        if user.has_pin:
            form.addRow("Current PIN", self.current)
        self.pin = _pin_field("Leave empty to remove the PIN" if user.has_pin else "New PIN")
        self.pin2 = _pin_field("Type it again")
        form.addRow("New PIN", self.pin)
        form.addRow("Confirm", self.pin2)
        lay.addLayout(form)
        self.error = QLabel("")
        self.error.setStyleSheet(f"color: {theme.CRITICAL};")
        lay.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Save", objectName="Primary")
        ok.setDefault(True)
        ok.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def _save(self):
        if self.user.has_pin and not users.check_pin(self.user, self.current.text()):
            self.error.setText("The current PIN is wrong.")
            return
        if self.pin.text() != self.pin2.text():
            self.error.setText("The two PINs don't match.")
            return
        if self.pin.text() and len(self.pin.text()) < 4:
            self.error.setText("Use at least 4 characters for the PIN.")
            return
        if not self.pin.text() and not self.user.has_pin:
            self.error.setText("Enter a PIN.")
            return
        users.set_pin_on(self.user, self.pin.text())
        users.update_user(self.user)
        self.accept()


class SignInDialog(QDialog):
    """'Who's using ModTender?' screen with user tiles and PIN entry."""

    MAX_TRIES, LOCK_SECONDS = 5, 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sign in to ModTender")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(560, 440)
        self.user: users.User | None = None
        self._selected: users.User | None = None
        self._fails: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 30, 36, 26)
        lay.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(56))
        logo.setFixedSize(56, 56)
        logo.setScaledContents(True)
        lay.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        head = QLabel("Who's using ModTender?", objectName="PageTitle")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(head)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(14)
        lay.addWidget(self.grid_host, 0, Qt.AlignmentFlag.AlignHCenter)

        self.pin_row = QWidget()
        pr = QHBoxLayout(self.pin_row)
        pr.setContentsMargins(0, 0, 0, 0)
        self.pin_label = QLabel("")
        self.pin = _pin_field()
        self.pin.setFixedWidth(180)
        self.pin.returnPressed.connect(self._try_pin)
        go = QPushButton("Sign in", objectName="Primary")
        go.clicked.connect(self._try_pin)
        pr.addStretch()
        pr.addWidget(self.pin_label)
        pr.addWidget(self.pin)
        pr.addWidget(go)
        pr.addStretch()
        self.pin_row.hide()
        lay.addWidget(self.pin_row)
        self.error = QLabel("")
        self.error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error.setStyleSheet(f"color: {theme.CRITICAL};")
        lay.addWidget(self.error)
        lay.addStretch()

        bottom = QHBoxLayout()
        add = QPushButton("Add user", objectName="Ghost")
        add.clicked.connect(self._add)
        bottom.addWidget(add)
        bottom.addStretch()
        note = QLabel("Each user has their own settings, theme and games.", objectName="Muted")
        bottom.addWidget(note)
        lay.addLayout(bottom)
        self._fill()

    def _fill(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        last = users.last_user_id()
        for i, u in enumerate(users.list_users()):
            b = QToolButton()
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setIcon(QIcon(avatar(u, 36)))
            b.setIconSize(QSize(72, 72))
            b.setText(u.name + ("  🔒" if u.has_pin else ""))
            b.setFixedSize(120, 120)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            border = theme.ACCENT if u.id == last else theme.BORDER
            b.setStyleSheet(f"QToolButton {{ background: {theme.SURFACE}; border: 1px solid {border}; border-radius: 12px;"
                            f" padding: 8px; font-weight: 600; }} QToolButton:hover {{ border-color: {theme.ACCENT}; }}")
            b.clicked.connect(lambda _=False, user=u: self._pick(user))
            self.grid.addWidget(b, i // 4, i % 4)

    def _pick(self, user: users.User):
        self.error.setText("")
        if not user.has_pin:
            self.user = user
            self.accept()
            return
        self._selected = user
        self.pin_label.setText(f"PIN for {user.name}:")
        self.pin.clear()
        self.pin_row.show()
        QTimer.singleShot(0, self.pin.setFocus)

    def _try_pin(self):
        u = self._selected
        if not u:
            return
        wait = self._locked_until.get(u.id, 0) - time.time()
        if wait > 0:
            self.error.setText(f"Too many wrong tries. Wait {int(wait) + 1} seconds.")
            return
        if users.check_pin(u, self.pin.text()):
            self.user = u
            self.accept()
            return
        self._fails[u.id] = self._fails.get(u.id, 0) + 1
        self.pin.clear()
        if self._fails[u.id] >= self.MAX_TRIES:
            self._fails[u.id] = 0
            self._locked_until[u.id] = time.time() + self.LOCK_SECONDS
            self.error.setText(f"Too many wrong tries. Wait {self.LOCK_SECONDS} seconds.")
        else:
            self.error.setText("Wrong PIN. Try again.")

    def _add(self):
        dlg = NewUserDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.user:
            self._fill()
            if not dlg.user.has_pin:
                self.user = dlg.user
                self.accept()
            else:
                self._pick(dlg.user)


def confirm_delete(parent, user: users.User) -> bool:
    if user.has_pin:
        from PySide6.QtWidgets import QInputDialog
        pin, ok = QInputDialog.getText(parent, "Delete user", f"Enter {user.name}'s PIN to delete this user:",
                                       QLineEdit.EchoMode.Password)
        if not ok or not users.check_pin(user, pin):
            if ok:
                QMessageBox.warning(parent, "Delete user", "Wrong PIN.")
            return False
    answer = QMessageBox.question(
        parent, "Delete user",
        f"Delete the user '{user.name}' and their settings?\n\nMods, backups and disabled mods on this PC aren't touched.")
    return answer == QMessageBox.StandardButton.Yes
