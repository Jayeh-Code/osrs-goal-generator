from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
        from PySide6.QtCore import QLockFile, QTimer
    except ModuleNotFoundError:
        print("PySide6 is not installed.")
        print("Install dependencies with: python -m pip install -r requirements.txt")
        return 1

    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JayehCode.OSRSGoalGenerator")
    app = QApplication(sys.argv)
    app.setApplicationName("OSRS Goal Generator")
    from osrs_goal_generator.config import DATA_DIR, STATE_FILE, ASSETS_DIR, VERSION
    from PySide6.QtGui import QIcon
    app.setWindowIcon(QIcon(str(ASSETS_DIR / "ui" / "app-icon.ico")))
    from osrs_goal_generator.services.save_migration import import_save, read_save
    lock = QLockFile(str(DATA_DIR / "app.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, "OSRS Goal Generator", "The app is already running. Close the other window before opening this copy.")
        return 1
    smoke = "--smoke-test" in sys.argv
    try:
        if not STATE_FILE.exists() and not smoke:
            legacy = ROOT / "user_data" / "state.json"
            if not getattr(sys, "frozen", False) and legacy.exists():
                import_save(legacy, STATE_FILE)
            else:
                answer = QMessageBox.question(None, "Welcome", "Do you have a save from an earlier version to import?\n\nChoose Yes and select desktop_app/user_data/state.json from your old app folder. Your original file will be kept.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer == QMessageBox.StandardButton.Yes:
                    source, _ = QFileDialog.getOpenFileName(None, "Select your previous state.json", "", "JSON saves (*.json)")
                    if not source:
                        return 0
                    import_save(Path(source), STATE_FILE)
        if STATE_FILE.exists():
            read_save(STATE_FILE)
    except (OSError, ValueError) as exc:
        QMessageBox.critical(None, "Save could not be loaded", f"Your save has not been replaced.\n\n{exc}\n\nSave folder: {DATA_DIR}\n\nRecovery: keep a copy of state.json first. In this folder, copy state.backup.json to state.json, then reopen the app. If needed, imported-original.json is the original imported save. Backups may contain older progress; keep the damaged file for recovery.")
        return 1
    from osrs_goal_generator.gui.main_window import MainWindow
    window = MainWindow()
    window.show()
    if smoke:
        import json
        report = Path(sys.argv[sys.argv.index("--smoke-test") + 1])
        def finish():
            from PySide6.QtGui import QPixmap
            icons = list((ASSETS_DIR / "bosses").glob("*.png"))
            result = {"version": VERSION, "frozen": bool(getattr(sys, "frozen", False)), "pages": window.pages.count(), "boss_icons": len(icons), "icons_readable": all(not QPixmap(str(p)).isNull() for p in icons), "data_dir": str(DATA_DIR)}
            window.grab().save(str(report.with_suffix(".png")))
            report.write_text(json.dumps(result, indent=2), encoding="utf-8")
            app.quit()
        QTimer.singleShot(1000, finish)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
