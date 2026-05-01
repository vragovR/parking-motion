from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from parking_motion.ui.thumbnail_service import ThumbnailService

FILE_THUMB_WIDTH = 96
FILE_THUMB_HEIGHT = 54

ACTIVE_FG = QColor("#1976d2")


def _set_item_progress(
    item: QListWidgetItem, name: str, percent: int, active: bool
) -> None:
    item.setText(f"{name} — {percent}%")
    item.setForeground(QBrush(ACTIVE_FG) if active else QBrush())


class FileListPanel(QWidget):
    filesSelected = Signal(object)
    fileClicked = Signal(object)

    def __init__(
        self,
        thumb_service: ThumbnailService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._thumb_service = thumb_service
        self._items_by_path: dict[Path, QListWidgetItem] = {}

        self._select_btn = QPushButton("Выбрать файлы…")
        self._select_btn.clicked.connect(self._on_select_clicked)

        self._label = QLabel("Файлы не выбраны")
        self._label.setWordWrap(True)
        self._label.setStyleSheet("color:#888;")

        self._list = QListWidget()
        self._list.setIconSize(QSize(FILE_THUMB_WIDTH, FILE_THUMB_HEIGHT))
        self._list.itemClicked.connect(self._on_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._select_btn)
        layout.addWidget(self._label)
        layout.addWidget(self._list, stretch=1)

        self._thumb_service.fileThumbnailReady.connect(self._on_thumb_ready)

    def set_files(self, paths: list[Path]) -> None:
        self._list.clear()
        self._items_by_path = {}
        for path in paths:
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(str(path))
            self._list.addItem(item)
            self._items_by_path[path] = item
            self._thumb_service.request_file_thumbnail(
                path, FILE_THUMB_WIDTH, FILE_THUMB_HEIGHT
            )
        self._label.setText(
            f"{len(paths)} файлов выбрано" if paths else "Файлы не выбраны"
        )

    def reset_for_new_run(self) -> None:
        for path, item in self._items_by_path.items():
            item.setText(path.name)
            item.setForeground(QBrush())

    def mark_progress(self, path: Path, percent: int, active: bool) -> None:
        item = self._items_by_path.get(path)
        if item is not None:
            _set_item_progress(item, path.name, percent, active)

    def mark_idle(self, path: Path) -> None:
        item = self._items_by_path.get(path)
        if item is not None:
            item.setForeground(QBrush())

    def set_selection_enabled(self, enabled: bool) -> None:
        self._select_btn.setEnabled(enabled)

    def _on_select_clicked(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите видеофайлы",
            "",
            "Видео (*.mp4 *.avi *.mkv *.mov)",
        )
        if not paths:
            return
        unique = sorted({Path(p) for p in paths}, key=lambda p: p.name.lower())
        self.filesSelected.emit(unique)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        path: Path = item.data(Qt.ItemDataRole.UserRole)
        self.fileClicked.emit(path)

    def _on_thumb_ready(self, path_str: str, image: QImage) -> None:
        item = self._items_by_path.get(Path(path_str))
        if item is not None:
            item.setIcon(QIcon(QPixmap.fromImage(image)))
