from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MotionParams:
    area_threshold: int = 1000
    mog_var_threshold: int = 16
    mog_history: int = 500
    mog_detect_shadows: bool = True
    blur_kernel: int = 0
    morph_kernel: int = 3
    min_contour_area: int = 150


@dataclass
class EventParams:
    merge_gap_s: float = 1.0
    min_duration_s: float = 1.0
    min_peak_area: int = 1500
    max_event_duration_s: float = 0.0
    cooldown_s: float = 0.0
    min_motion_frames: int = 2


@dataclass
class ExportParams:
    pad_before_s: float = 0.0
    pad_after_s: float = 0.0
    fourcc: str = "mp4v"


@dataclass
class ProcessingParams:
    frame_skip: int = 5
    parallel_workers: int = 2
    motion: MotionParams = field(default_factory=MotionParams)
    event: EventParams = field(default_factory=EventParams)
    export: ExportParams = field(default_factory=ExportParams)


@dataclass
class SessionState:
    files: list[Path] = field(default_factory=list)
    roi: tuple[int, int, int, int] | None = None
