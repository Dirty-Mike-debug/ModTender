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
    window = MainWindow()
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


if __name__ == "__main__":
    sys.exit(main())
