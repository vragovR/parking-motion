import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from parking_motion.config import ExportParams
from parking_motion.core.events import Event
from parking_motion.core.exporter import export_clip, export_concatenated


class ExportWorker(QObject):
    started = Signal(int)
    progress = Signal(int, int)
    clipDone = Signal(object, object)
    clipFailed = Signal(object, str)
    finished = Signal()

    def __init__(
        self,
        jobs: list[tuple[Event, Path]],
        params: ExportParams,
    ) -> None:
        super().__init__()
        self._jobs = list(jobs)
        self._params = params
        self._cancel_event = threading.Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        total = len(self._jobs)
        self.started.emit(total)
        done = 0
        for event, dst in self._jobs:
            if self._cancel_event.is_set():
                break
            try:
                export_clip(
                    source=event.source,
                    start_s=event.start_s,
                    end_s=event.end_s,
                    dst=dst,
                    pad_before_s=self._params.pad_before_s,
                    pad_after_s=self._params.pad_after_s,
                    fourcc=self._params.fourcc,
                    cancel_event=self._cancel_event,
                )
                self.clipDone.emit(event, dst)
            except Exception as e:
                self.clipFailed.emit(event, repr(e))
            done += 1
            self.progress.emit(done, total)
        self.finished.emit()


class ConcatExportWorker(QObject):
    started = Signal(int)
    progress = Signal(int, int)
    clipDone = Signal(object, object)
    clipFailed = Signal(object, str)
    finished = Signal()

    def __init__(
        self,
        events: list[Event],
        dst: Path,
        params: ExportParams,
    ) -> None:
        super().__init__()
        self._events = list(events)
        self._dst = dst
        self._params = params
        self._cancel_event = threading.Event()
        self._done_count = 0
        self._total = len(events)

    def request_cancel(self) -> None:
        self._cancel_event.set()

    def _on_event_done(self, event: Event) -> None:
        self._done_count += 1
        self.progress.emit(self._done_count, self._total)

    @Slot()
    def run(self) -> None:
        self.started.emit(self._total)
        try:
            export_concatenated(
                events=self._events,
                dst=self._dst,
                pad_before_s=self._params.pad_before_s,
                pad_after_s=self._params.pad_after_s,
                fourcc=self._params.fourcc,
                cancel_event=self._cancel_event,
                on_event_done=self._on_event_done,
            )
            self.clipDone.emit(self._events[0] if self._events else None, self._dst)
        except Exception as e:
            target = self._events[0] if self._events else None
            self.clipFailed.emit(target, repr(e))
        self.finished.emit()
