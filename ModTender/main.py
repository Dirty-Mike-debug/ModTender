"""Start ModTender."""
import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("ModTender needs PySide6. Install it with:  pip install -r requirements.txt")
        return 1

    from modtender import APP_NAME
    from modtender.core.log import setup as setup_log

    setup_log()
    from modtender.ui.main_window import MainWindow

    if sys.platform == "win32":
        # Give ModTender its own taskbar icon group instead of python.exe's.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ModTender.App")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")

    user = sign_in(app, force=False)
    if user is None:
        return 0
    window = MainWindow(user)
    window.show()
    if "--self-test" in sys.argv:
        # Used by the release build: open the full window, then report success and quit.
        import os
        from PySide6.QtCore import QTimer

        def finish():
            out = os.environ.get("MODTENDER_SELFTEST_OUT")
            if out:
                with open(out, "w", encoding="utf-8") as fh:
                    fh.write(f"ok {window.windowTitle()} pages={len(window.pages)} games={len(window.games)}")
            app.quit()

        QTimer.singleShot(4000, finish)
        return app.exec()

    while True:
        code = app.exec()
        if not window.switch_requested:
            return code
        user = sign_in(app, force=True)  # "Switch user": show the sign-in screen again
        if user is None:
            return code
        window = MainWindow(user)
        window.show()


def sign_in(app, force: bool):
    """Pick the user for this session. Returns None if the sign-in screen was closed."""
    from PySide6.QtWidgets import QDialog

    from modtender.core import settings, users
    from modtender.ui import theme
    from modtender.ui.signin import SignInDialog

    first = users.ensure_first_user()
    settings.use_user(first.id)  # show the sign-in screen in the last user's theme
    s = settings.load_settings()
    theme.apply(app, s.theme_preset, s.theme_overrides)
    user = first
    if force or users.needs_signin():
        dlg = SignInDialog()
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.user is None:
            return None
        user = dlg.user
    users.set_last_user(user)
    settings.use_user(user.id)
    return user


if __name__ == "__main__":
    sys.exit(main())
