from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError:
        print("PySide6 is not installed.")
        print("Install dependencies with: python -m pip install -r requirements.txt")
        return 1

    from osrs_goal_generator.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("OSRS Goal Generator")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
