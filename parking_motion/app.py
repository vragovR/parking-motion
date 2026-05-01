import sys

from PySide6.QtWidgets import QApplication

from parking_motion.config import ProcessingParams
from parking_motion.ui.main_window import MainWindow


def run() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Parking Motion")
    window = MainWindow(ProcessingParams())
    window.show()
    sys.exit(app.exec())
