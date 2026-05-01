from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage


def _decode_thumbnail(
    path: Path, t_seconds: float, max_w: int, max_h: int
) -> QImage | None:
    cap = cv2.VideoCapture(str(path))
    try:
        if t_seconds > 0:
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t_seconds) * 1000.0)
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok or frame is None:
        return None
    h, w = frame.shape[:2]
    if w == 0 or h == 0:
        return None
    scale = min(max_w / w, max_h / h)
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))
    frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return QImage(rgb.data, nw, nh, 3 * nw, QImage.Format.Format_RGB888).copy()


class ThumbnailService(QObject):
    fileThumbnailReady = Signal(str, QImage)
    eventThumbnailReady = Signal(str, float, QImage)

    def __init__(self, max_workers: int = 2, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="thumb"
        )

    def request_file_thumbnail(self, path: Path, max_w: int, max_h: int) -> None:
        self._pool.submit(self._do_file, path, max_w, max_h)

    def request_event_thumbnail(
        self,
        path: Path,
        key_start_s: float,
        frame_t_seconds: float,
        max_w: int,
        max_h: int,
    ) -> None:
        self._pool.submit(
            self._do_event, path, key_start_s, frame_t_seconds, max_w, max_h
        )

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _do_file(self, path: Path, max_w: int, max_h: int) -> None:
        img = _decode_thumbnail(path, 0.0, max_w, max_h)
        if img is not None:
            self.fileThumbnailReady.emit(str(path), img)

    def _do_event(
        self,
        path: Path,
        key_start_s: float,
        frame_t_seconds: float,
        max_w: int,
        max_h: int,
    ) -> None:
        img = _decode_thumbnail(path, frame_t_seconds, max_w, max_h)
        if img is not None:
            self.eventThumbnailReady.emit(str(path), key_start_s, img)
