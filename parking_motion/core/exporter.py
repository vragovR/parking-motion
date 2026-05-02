import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import cv2

from parking_motion.core.events import Event


def default_clip_filename(source: Path, start_s: float, duration_s: float) -> str:
    s = max(0.0, start_s)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    return f"{source.stem}_{h:02d}-{m:02d}-{sec:02d}_{max(0.0, duration_s):.1f}s.mp4"


def dedupe_filename(directory: Path, name: str, taken: set[str]) -> str:
    stem = Path(name).stem
    suffix = Path(name).suffix
    candidate = name
    n = 2
    while candidate in taken or (directory / candidate).exists():
        candidate = f"{stem}_{n}{suffix}"
        n += 1
    return candidate


class ExportError(RuntimeError):
    pass


def export_clip(
    source: Path,
    start_s: float,
    end_s: float,
    dst: Path,
    pad_before_s: float = 0.0,
    pad_after_s: float = 0.0,
    fourcc: str = "mp4v",
    cancel_event: threading.Event | None = None,
) -> Path:
    cap = cv2.VideoCapture(str(source))
    try:
        if not cap.isOpened():
            raise ExportError(f"cannot open source: {source}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

        if width <= 0 or height <= 0:
            raise ExportError(f"invalid frame size {width}x{height} for {source}")

        clip_start_s = max(0.0, start_s - max(0.0, pad_before_s))
        clip_end_s = end_s + max(0.0, pad_after_s)
        if total_frames > 0:
            clip_end_s = min(clip_end_s, total_frames / fps)
        if clip_end_s <= clip_start_s:
            raise ExportError(f"empty clip range for {source} [{clip_start_s}; {clip_end_s}]")

        start_frame = max(0, int(round(clip_start_s * fps)))
        end_frame = max(start_frame + 1, int(round(clip_end_s * fps)))

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        dst.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*fourcc), fps, (width, height))
        if not writer.isOpened():
            raise ExportError(f"cannot open writer for {dst} (fourcc={fourcc})")

        try:
            frames_to_write = end_frame - start_frame
            for _ in range(frames_to_write):
                if cancel_event is not None and cancel_event.is_set():
                    break
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                writer.write(frame)
        finally:
            writer.release()
        return dst
    finally:
        cap.release()


def export_concatenated(
    events: Sequence[Event],
    dst: Path,
    pad_before_s: float = 0.0,
    pad_after_s: float = 0.0,
    fourcc: str = "mp4v",
    cancel_event: threading.Event | None = None,
    on_event_done: Callable[[Event], None] | None = None,
) -> Path:
    if not events:
        raise ExportError("no events to concatenate")

    first = events[0]
    probe = cv2.VideoCapture(str(first.source))
    try:
        if not probe.isOpened():
            raise ExportError(f"cannot open source: {first.source}")
        fps = probe.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(probe.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(probe.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        probe.release()

    if width <= 0 or height <= 0:
        raise ExportError(f"invalid frame size {width}x{height} for {first.source}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*fourcc), fps, (width, height))
    if not writer.isOpened():
        raise ExportError(f"cannot open writer for {dst} (fourcc={fourcc})")

    try:
        for ev in events:
            if cancel_event is not None and cancel_event.is_set():
                break
            cap = cv2.VideoCapture(str(ev.source))
            try:
                if not cap.isOpened():
                    continue
                src_fps = cap.get(cv2.CAP_PROP_FPS) or fps
                src_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

                clip_start_s = max(0.0, ev.start_s - max(0.0, pad_before_s))
                clip_end_s = ev.end_s + max(0.0, pad_after_s)
                if src_total > 0:
                    clip_end_s = min(clip_end_s, src_total / src_fps)
                if clip_end_s <= clip_start_s:
                    continue

                start_frame = max(0, int(round(clip_start_s * src_fps)))
                end_frame = max(start_frame + 1, int(round(clip_end_s * src_fps)))
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                for _ in range(end_frame - start_frame):
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        break
                    if frame.shape[1] != width or frame.shape[0] != height:
                        frame = cv2.resize(frame, (width, height))
                    writer.write(frame)
            finally:
                cap.release()
            if on_event_done is not None:
                on_event_done(ev)
    finally:
        writer.release()
    return dst
