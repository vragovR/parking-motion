import time
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from parking_motion.config import ProcessingParams
from parking_motion.core.events import Event
from parking_motion.ui.worker import ProcessingWorker


def _format_elapsed(seconds: float) -> str:
    seconds = int(max(0.0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class ProcessingController(QObject):
    runStarted = Signal(int)
    runFinished = Signal(object)
    fileStarted = Signal(object)
    fileProgress = Signal(object, int, float)
    fileFinished = Signal(object)
    overallProgress = Signal(int, int)
    eventFound = Signal(object)
    elapsedTick = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None
        self._active_paths: set[Path] = set()
        self._completed_count = 0
        self._total_count = 0
        self._started_at: float | None = None
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

    def is_running(self) -> bool:
        return self._thread is not None

    def start(
        self,
        files: list[Path],
        roi: tuple[int, int, int, int],
        params: ProcessingParams,
    ) -> None:
        if self._thread is not None:
            return
        self._active_paths = set()
        self._completed_count = 0
        self._total_count = len(files)
        self._started_at = time.monotonic()

        self._worker = ProcessingWorker(
            params=params,
            files=files,
            roi=roi,
            max_workers=params.parallel_workers,
        )
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.fileStarted.connect(self._on_worker_file_started)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.eventFound.connect(self._on_worker_event_found)
        self._worker.finished.connect(self._on_worker_finished)

        self.runStarted.emit(self._total_count)
        self.overallProgress.emit(0, self._total_count)
        self._tick_elapsed()
        self._elapsed_timer.start()
        self._thread.start()

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()

    def shutdown(self, timeout_ms: int = 3000) -> None:
        if self._worker is not None:
            self._worker.request_cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(timeout_ms)
        self._elapsed_timer.stop()

    def _on_worker_file_started(self, path_str: str) -> None:
        path = Path(path_str)
        self._active_paths.add(path)
        self.fileStarted.emit(path)

    def _on_worker_progress(self, path_str: str, percent: int, eta: float) -> None:
        path = Path(path_str)
        if percent >= 100:
            if path in self._active_paths:
                self._active_paths.discard(path)
                self._completed_count += 1
                self.overallProgress.emit(self._completed_count, self._total_count)
            self.fileFinished.emit(path)
        else:
            self.fileProgress.emit(path, percent, eta)

    def _on_worker_event_found(self, event: Event) -> None:
        self.eventFound.emit(event)

    def _on_worker_finished(self) -> None:
        self._elapsed_timer.stop()
        self._tick_elapsed()

        thread = self._thread
        worker = self._worker
        self._thread = None
        self._worker = None
        if thread is not None:
            thread.quit()
            thread.wait()
            thread.deleteLater()
        if worker is not None:
            worker.deleteLater()

        stranded = sorted(self._active_paths, key=lambda p: p.name.lower())
        self._active_paths.clear()
        self.runFinished.emit(stranded)

    def _tick_elapsed(self) -> None:
        if self._started_at is None:
            return
        self.elapsedTick.emit(_format_elapsed(time.monotonic() - self._started_at))
