from pathlib import Path

from parking_motion.config import ProcessingParams
from parking_motion.core.processor import VideoProcessor


def run_processing(
    path: Path,
    roi: tuple[int, int, int, int],
    params: ProcessingParams,
    msg_queue,
    cancel_event,
) -> None:
    msg_queue.put(("started", str(path)))
    try:
        VideoProcessor(params).process_file(
            path=path,
            roi=roi,
            on_event=lambda ev: msg_queue.put(("event", ev)),
            on_progress=lambda p, pct, eta: msg_queue.put(("progress", str(p), pct, eta)),
            cancel_event=cancel_event,
        )
    except Exception as e:
        msg_queue.put(("error", str(path), repr(e)))
