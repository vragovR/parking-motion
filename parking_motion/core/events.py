from dataclasses import dataclass
from pathlib import Path

from parking_motion.config import EventParams
from parking_motion.core.motion import MotionSample


@dataclass
class Event:
    source: Path
    start_s: float
    end_s: float
    duration_s: float
    peak_area: int
    mean_area: float


class EventAggregator:
    def __init__(self, source: Path, params: EventParams) -> None:
        self._source = source
        self._merge_gap_s = params.merge_gap_s
        self._min_duration_s = params.min_duration_s
        self._min_peak_area = max(0, params.min_peak_area)
        self._max_event_duration_s = max(0.0, params.max_event_duration_s)
        self._cooldown_s = max(0.0, params.cooldown_s)
        self._min_motion_frames = max(1, params.min_motion_frames)
        self._start_s: float | None = None
        self._last_s: float | None = None
        self._peak: int = 0
        self._sum: int = 0
        self._count: int = 0
        self._cooldown_until: float = 0.0

    def feed(self, sample: MotionSample) -> Event | None:
        if sample.t_seconds < self._cooldown_until:
            return None

        closed: Event | None = None

        if self._last_s is not None and sample.t_seconds - self._last_s > self._merge_gap_s:
            closed = self._close()
            self._reset()
            if sample.t_seconds < self._cooldown_until:
                return closed
        elif (
            self._start_s is not None
            and self._max_event_duration_s > 0.0
            and sample.t_seconds - self._start_s >= self._max_event_duration_s
        ):
            closed = self._close()
            self._reset()
            if sample.t_seconds < self._cooldown_until:
                return closed

        if self._start_s is None:
            self._start_s = sample.t_seconds
        self._last_s = sample.t_seconds
        self._peak = max(self._peak, sample.area)
        self._sum += sample.area
        self._count += 1
        return closed

    def flush(self) -> Event | None:
        ev = self._close()
        self._reset()
        return ev

    def _close(self) -> Event | None:
        if self._start_s is None or self._last_s is None or self._count == 0:
            return None
        duration = self._last_s - self._start_s
        if duration < self._min_duration_s:
            return None
        if self._count < self._min_motion_frames:
            return None
        if self._peak < self._min_peak_area:
            return None
        ev = Event(
            source=self._source,
            start_s=self._start_s,
            end_s=self._last_s,
            duration_s=duration,
            peak_area=self._peak,
            mean_area=self._sum / self._count,
        )
        self._cooldown_until = ev.end_s + self._cooldown_s
        return ev

    def _reset(self) -> None:
        self._start_s = None
        self._last_s = None
        self._peak = 0
        self._sum = 0
        self._count = 0
