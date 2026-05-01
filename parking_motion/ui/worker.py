import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from queue import Empty

from PySide6.QtCore import QObject, Signal, Slot

from parking_motion.config import ProcessingParams
from parking_motion.core.subprocess_runner import run_processing


class ProcessingWorker(QObject):
    eventFound = Signal(object)
    progress = Signal(str, int, float)
    fileStarted = Signal(str)
    finished = Signal()

    def __init__(
        self,
        params: ProcessingParams,
        files: list[Path],
        roi: tuple[int, int, int, int],
        max_workers: int,
    ) -> None:
        super().__init__()
        self._params = params
        self._files = list(files)
        self._roi = roi
        self._max_workers = max(1, max_workers)
        self._cancel_lock = threading.Lock()
        self._cancel_event = None

    def request_cancel(self) -> None:
        with self._cancel_lock:
            if self._cancel_event is not None:
                self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        manager = multiprocessing.Manager()
        try:
            queue = manager.Queue()
            with self._cancel_lock:
                self._cancel_event = manager.Event()
            cancel_event = self._cancel_event

            with ProcessPoolExecutor(max_workers=self._max_workers) as pool:
                fut_to_path = {
                    pool.submit(
                        run_processing,
                        p,
                        self._roi,
                        self._params,
                        queue,
                        cancel_event,
                    ): p
                    for p in self._files
                }
                pending = set(fut_to_path.values())

                while pending:
                    try:
                        msg = queue.get(timeout=0.2)
                    except Empty:
                        msg = None

                    if msg is not None:
                        kind = msg[0]
                        if kind == "started":
                            self.fileStarted.emit(msg[1])
                        elif kind == "event":
                            self.eventFound.emit(msg[1])
                        elif kind == "progress":
                            self.progress.emit(msg[1], msg[2], msg[3])
                            if msg[2] >= 100:
                                pending.discard(Path(msg[1]))
                        elif kind == "error":
                            pending.discard(Path(msg[1]))
                            self.progress.emit(msg[1], 100, 0.0)

                    for fut, p in list(fut_to_path.items()):
                        if fut.done() and p in pending:
                            pending.discard(p)
                            self.progress.emit(str(p), 100, 0.0)
        finally:
            try:
                manager.shutdown()
            except Exception:
                pass
            self.finished.emit()
