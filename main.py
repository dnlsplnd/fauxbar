import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    style_path = Path(__file__).parent / "app" / "style.qss"
    app.setStyleSheet(style_path.read_text())

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
