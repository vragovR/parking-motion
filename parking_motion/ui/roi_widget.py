from pathlib import Path

import cv2
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPaintEvent, QPen, QPixmap
from PySide6.QtWidgets import QLabel


class RoiCanvas(QLabel):
    roiSelected = Signal(tuple)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(640, 360)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#222;color:#888;")
        self.setText("Выберите файл из списка слева, чтобы разметить ROI")
        self._frame_pixmap: QPixmap | None = None
        self._frame_size: tuple[int, int] | None = None
        self._dragging = False
        self._drag_start: QPoint | None = None
        self._drag_end: QPoint | None = None
        self._roi_frame: tuple[int, int, int, int] | None = None

    def set_video(self, path: Path) -> None:
        cap = cv2.VideoCapture(str(path))
        try:
            ok, frame = cap.read()
        finally:
            cap.release()
        if not ok or frame is None:
            self.setText(f"Не удалось прочитать кадр из {path.name}")
            self._frame_pixmap = None
            self._frame_size = None
            return
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        self._frame_pixmap = QPixmap.fromImage(image)
        self._frame_size = (w, h)
        self._roi_frame = None
        self.setText("")
        self.update()

    def set_roi_from_frame(self, roi: tuple[int, int, int, int] | None) -> None:
        if roi is None or self._frame_size is None:
            self._roi_frame = None
        else:
            self._roi_frame = roi
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._frame_pixmap is None:
            return
        painter = QPainter(self)
        target_rect = self._image_target_rect()
        painter.drawPixmap(target_rect, self._frame_pixmap)
        rect_to_draw: QRect | None = None
        if self._dragging and self._drag_start is not None and self._drag_end is not None:
            rect_to_draw = QRect(self._drag_start, self._drag_end).normalized()
        elif self._roi_frame is not None:
            rect_to_draw = self._frame_to_widget_rect(self._roi_frame)
        if rect_to_draw is not None:
            pen = QPen(Qt.GlobalColor.green)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(rect_to_draw)

    def mousePressEvent(self, event) -> None:
        if self._frame_pixmap is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.position().toPoint()
            self._drag_end = self._drag_start
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        self._drag_end = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self._dragging or event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = False
        self._drag_end = event.position().toPoint()
        if self._drag_start is None or self._drag_end is None:
            return
        widget_rect = QRect(self._drag_start, self._drag_end).normalized()
        if widget_rect.width() < 5 or widget_rect.height() < 5:
            return
        roi = self._widget_rect_to_frame(widget_rect)
        if roi is None:
            return
        self._roi_frame = roi
        self.update()
        self.roiSelected.emit(roi)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update()

    def _image_target_rect(self) -> QRect:
        if self._frame_pixmap is None:
            return self.rect()
        widget_w = self.width()
        widget_h = self.height()
        pix_w = self._frame_pixmap.width()
        pix_h = self._frame_pixmap.height()
        if pix_w == 0 or pix_h == 0:
            return self.rect()
        scale = min(widget_w / pix_w, widget_h / pix_h)
        target_w = int(pix_w * scale)
        target_h = int(pix_h * scale)
        x = (widget_w - target_w) // 2
        y = (widget_h - target_h) // 2
        return QRect(x, y, target_w, target_h)

    def _widget_rect_to_frame(
        self, widget_rect: QRect
    ) -> tuple[int, int, int, int] | None:
        if self._frame_size is None:
            return None
        target = self._image_target_rect()
        if target.width() == 0 or target.height() == 0:
            return None
        clipped = widget_rect.intersected(target)
        if clipped.isEmpty():
            return None
        fw, fh = self._frame_size
        sx = fw / target.width()
        sy = fh / target.height()
        x = int((clipped.x() - target.x()) * sx)
        y = int((clipped.y() - target.y()) * sy)
        w = int(clipped.width() * sx)
        h = int(clipped.height() * sy)
        x = max(0, min(x, fw - 1))
        y = max(0, min(y, fh - 1))
        w = max(1, min(w, fw - x))
        h = max(1, min(h, fh - y))
        return (x, y, w, h)

    def _frame_to_widget_rect(self, roi: tuple[int, int, int, int]) -> QRect:
        target = self._image_target_rect()
        if self._frame_size is None or target.width() == 0 or target.height() == 0:
            return QRect()
        fw, fh = self._frame_size
        sx = target.width() / fw
        sy = target.height() / fh
        x, y, w, h = roi
        return QRect(
            target.x() + int(x * sx),
            target.y() + int(y * sy),
            int(w * sx),
            int(h * sy),
        )
