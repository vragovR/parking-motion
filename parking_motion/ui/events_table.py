import bisect
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QPixmap

from parking_motion.core.events import Event


def _sort_key(event: Event) -> tuple[str, float]:
    return (event.source.name.lower(), event.start_s)


COLUMNS = ("Превью", "Файл", "Начало", "Длительность, с", "")


def format_hms(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


class EventsModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._events: list[Event] = []
        self._thumbs: list[QPixmap | None] = []
        self._keys: list[tuple[str, float]] = []

    def add_event(self, event: Event, thumbnail: QPixmap | None = None) -> None:
        key = _sort_key(event)
        row = bisect.bisect_right(self._keys, key)
        self.beginInsertRows(QModelIndex(), row, row)
        self._keys.insert(row, key)
        self._events.insert(row, event)
        self._thumbs.insert(row, thumbnail)
        self.endInsertRows()

    def clear(self) -> None:
        if not self._events:
            return
        self.beginResetModel()
        self._events = []
        self._thumbs = []
        self._keys = []
        self.endResetModel()

    def set_thumb_for_event(self, source: Path, start_s: float, pixmap: QPixmap) -> None:
        key = (source.name.lower(), start_s)
        row = bisect.bisect_left(self._keys, key)
        while row < len(self._events) and self._keys[row] == key:
            if self._events[row].source == source:
                self._thumbs[row] = pixmap
                idx = self.index(row, 0)
                self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])
                return
            row += 1

    def event_at(self, row: int) -> Event | None:
        if 0 <= row < len(self._events):
            return self._events[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._events)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(COLUMNS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        ev = self._events[row]
        col = index.column()
        if role == Qt.ItemDataRole.DecorationRole and col == 0:
            return self._thumbs[row]
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 1:
                return ev.source.name
            if col == 2:
                return format_hms(ev.start_s)
            if col == 3:
                return f"{ev.duration_s:.2f}"
        if role == Qt.ItemDataRole.ToolTipRole and col == 1:
            return str(ev.source)
        if role == Qt.ItemDataRole.UserRole:
            return ev
        return None
