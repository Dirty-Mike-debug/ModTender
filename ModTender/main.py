"""Start ModTender."""
import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("ModTender needs PySide6. Install it with:  pip install -r requirements.txt")
        return 1

    from modtender import APP_NAME
    from modtender.ui.main_window import MainWindow
    from modtender.ui.theme import STYLESHEET

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
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
