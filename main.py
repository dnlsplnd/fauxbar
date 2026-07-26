import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    style_path = base_path / "app" / "style.qss"
    app.setStyleSheet(style_path.read_text())
    app.setWindowIcon(QIcon(str(base_path / "assets" / "fauxbar.png")))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
