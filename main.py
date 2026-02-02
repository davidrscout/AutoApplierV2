import sys

from PySide6 import QtWidgets

from autoapplier.ui.main_window import MainWindow
from autoapplier.core.utils import ensure_dirs


def main() -> None:
    ensure_dirs()
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
