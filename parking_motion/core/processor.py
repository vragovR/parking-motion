import threading
import time
from collections.abc import Callable
from pathlib import Path

import cv2

from parking_motion.config import ProcessingParams
from parking_motion.core.events import Event, EventAggregator
from parking_motion.core.motion import RoiMotionDetector

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mkv", ".mov")


def iter_video_files(directory: Path) -> list[Path]:
    return sorted(
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )


ProgressCallback = Callable[[Path, int, float], None]
EventCallback = Callable[[Event], None]


class VideoProcessor:
    def __init__(self, params: ProcessingParams) -> None:
        self._params = params

    def process_file(
        self,
        path: Path,
        roi: tuple[int, int, int, int],
        on_event: EventCallback,
        on_progress: ProgressCallback,
        cancel_event: threading.Event,
    ) -> None:
        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened():
                return
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

            detector = RoiMotionDetector(roi=roi, params=self._params.motion)
            aggregator = EventAggregator(source=path, params=self._params.event)

            frame_skip = max(1, self._params.frame_skip)
            processed = 0
            grabbed_total = 0
            started = time.monotonic()

            while True:
                if cancel_event.is_set():
                    return

                for _ in range(frame_skip - 1):
                    if not cap.grab():
                        break
                    grabbed_total += 1

                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                grabbed_total += 1

                t_seconds = grabbed_total / fps
                sample = detector.process(frame, t_seconds)
                if sample is not None:
                    closed = aggregator.feed(sample)
                    if closed is not None:
                        on_event(closed)

                processed += 1
                if processed % 30 == 0 and total_frames > 0:
                    percent = int(grabbed_total * 100 / total_frames)
                    elapsed = time.monotonic() - started
                    eta = elapsed / max(1, grabbed_total) * max(0, total_frames - grabbed_total)
                    on_progress(path, percent, eta)

            tail = aggregator.flush()
            if tail is not None:
                on_event(tail)
            on_progress(path, 100, 0.0)
        finally:
            cap.release()
