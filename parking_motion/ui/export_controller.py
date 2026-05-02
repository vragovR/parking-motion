from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from parking_motion.config import ExportParams
from parking_motion.core.events import Event
from parking_motion.ui.export_worker import ConcatExportWorker, ExportWorker


class ExportController(QObject):
    exportStarted = Signal(int)
    exportProgress = Signal(int, int)
    clipDone = Signal(object, object)
    clipFailed = Signal(object, str)
    exportFinished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: ExportWorker | ConcatExportWorker | None = None

    def is_running(self) -> bool:
        return self._thread is not None

    def export_one(self, event: Event, dst: Path, params: ExportParams) -> None:
        self._run_worker(ExportWorker([(event, dst)], params))

    def export_many(self, jobs: list[tuple[Event, Path]], params: ExportParams) -> None:
        if not jobs:
            return
        self._run_worker(ExportWorker(jobs, params))

    def export_concat(self, events: list[Event], dst: Path, params: ExportParams) -> None:
        if not events:
            return
        self._run_worker(ConcatExportWorker(events, dst, params))

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()

    def shutdown(self, timeout_ms: int = 3000) -> None:
        if self._worker is not None:
            self._worker.request_cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(timeout_ms)

    def _run_worker(self, worker: ExportWorker | ConcatExportWorker) -> None:
        if self._thread is not None:
            return
        self._worker = worker
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.started.connect(self.exportStarted)
        self._worker.progress.connect(self.exportProgress)
        self._worker.clipDone.connect(self.clipDone)
        self._worker.clipFailed.connect(self.clipFailed)
        self._worker.finished.connect(self._on_worker_finished)
        self._thread.start()

    def _on_worker_finished(self) -> None:
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
        self.exportFinished.emit()
