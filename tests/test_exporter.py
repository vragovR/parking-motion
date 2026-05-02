from pathlib import Path

import cv2
import numpy as np
import pytest

from parking_motion.core.events import Event
from parking_motion.core.exporter import (
    ExportError,
    dedupe_filename,
    default_clip_filename,
    export_clip,
    export_concatenated,
)


def test_default_filename_basic_format() -> None:
    name = default_clip_filename(Path("/v/cam01.mp4"), start_s=125.7, duration_s=4.25)
    assert name == "cam01_00-02-05_4.2s.mp4"


def test_default_filename_zero_clamps_negative_start() -> None:
    name = default_clip_filename(Path("foo.mkv"), start_s=-3.0, duration_s=2.0)
    assert name == "foo_00-00-00_2.0s.mp4"


def test_default_filename_handles_hours() -> None:
    name = default_clip_filename(Path("rec.mp4"), start_s=3725.0, duration_s=10.0)
    assert name == "rec_01-02-05_10.0s.mp4"


def test_dedupe_passthrough_when_unique(tmp_path: Path) -> None:
    assert dedupe_filename(tmp_path, "a.mp4", taken=set()) == "a.mp4"


def test_dedupe_appends_suffix_when_in_taken(tmp_path: Path) -> None:
    taken = {"a.mp4"}
    assert dedupe_filename(tmp_path, "a.mp4", taken) == "a_2.mp4"


def test_dedupe_appends_suffix_when_file_exists(tmp_path: Path) -> None:
    (tmp_path / "a.mp4").write_bytes(b"x")
    assert dedupe_filename(tmp_path, "a.mp4", taken=set()) == "a_2.mp4"


def test_dedupe_walks_through_collisions(tmp_path: Path) -> None:
    (tmp_path / "a.mp4").write_bytes(b"x")
    taken = {"a_2.mp4"}
    assert dedupe_filename(tmp_path, "a.mp4", taken) == "a_3.mp4"


def _write_synthetic_video(path: Path, frames: int = 30, fps: float = 10.0) -> bool:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (64, 48))
    if not writer.isOpened():
        return False
    try:
        for i in range(frames):
            frame = np.full((48, 64, 3), i * 8 % 255, dtype=np.uint8)
            writer.write(frame)
    finally:
        writer.release()
    return path.exists() and path.stat().st_size > 0


def test_export_clip_smoke(tmp_path: Path) -> None:
    src = tmp_path / "src.mp4"
    if not _write_synthetic_video(src):
        pytest.skip("mp4v codec unavailable for synthetic video")

    dst = tmp_path / "out.mp4"
    export_clip(src, start_s=0.5, end_s=2.0, dst=dst)
    assert dst.exists()
    assert dst.stat().st_size > 0

    cap = cv2.VideoCapture(str(dst))
    try:
        assert cap.isOpened()
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        assert n > 0
    finally:
        cap.release()


def test_export_clip_raises_on_missing_source(tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        export_clip(tmp_path / "nope.mp4", 0.0, 1.0, tmp_path / "out.mp4")


def test_export_concatenated_raises_on_empty() -> None:
    with pytest.raises(ExportError):
        export_concatenated([], Path("/tmp/x.mp4"))


def test_export_concatenated_smoke(tmp_path: Path) -> None:
    src = tmp_path / "src.mp4"
    if not _write_synthetic_video(src, frames=60, fps=10.0):
        pytest.skip("mp4v codec unavailable for synthetic video")

    events = [
        Event(source=src, start_s=0.5, end_s=1.5, duration_s=1.0, peak_area=0, mean_area=0.0),
        Event(source=src, start_s=3.0, end_s=4.5, duration_s=1.5, peak_area=0, mean_area=0.0),
    ]
    dst = tmp_path / "merged.mp4"
    seen: list[Event] = []
    export_concatenated(events, dst, on_event_done=seen.append)
    assert dst.exists()
    assert dst.stat().st_size > 0
    assert len(seen) == 2

    cap = cv2.VideoCapture(str(dst))
    try:
        assert cap.isOpened()
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        assert n > 0
    finally:
        cap.release()
