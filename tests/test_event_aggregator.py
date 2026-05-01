from dataclasses import replace
from pathlib import Path

import pytest

from parking_motion.config import EventParams
from parking_motion.core.events import EventAggregator
from parking_motion.core.motion import MotionSample


SOURCE = Path("/tmp/fake.mp4")


def make_params(**overrides) -> EventParams:
    base = EventParams(
        merge_gap_s=1.0,
        min_duration_s=0.0,
        min_peak_area=0,
        max_event_duration_s=0.0,
        cooldown_s=0.0,
        min_motion_frames=1,
    )
    return replace(base, **overrides)


def feed_all(agg: EventAggregator, samples: list[tuple[float, int]]) -> list:
    out = []
    for t, area in samples:
        ev = agg.feed(MotionSample(t_seconds=t, area=area))
        if ev is not None:
            out.append(ev)
    tail = agg.flush()
    if tail is not None:
        out.append(tail)
    return out


def test_flush_without_feed_returns_none() -> None:
    agg = EventAggregator(SOURCE, make_params())
    assert agg.flush() is None


def test_short_event_dropped_by_min_duration() -> None:
    agg = EventAggregator(SOURCE, make_params(min_duration_s=1.0))
    events = feed_all(agg, [(0.0, 100), (0.4, 100)])
    assert events == []


def test_event_meeting_min_duration_emitted_on_flush() -> None:
    agg = EventAggregator(SOURCE, make_params(min_duration_s=1.0))
    events = feed_all(agg, [(0.0, 100), (0.5, 200), (1.0, 150)])
    assert len(events) == 1
    ev = events[0]
    assert ev.source == SOURCE
    assert ev.start_s == 0.0
    assert ev.end_s == 1.0
    assert ev.duration_s == pytest.approx(1.0)
    assert ev.peak_area == 200
    assert ev.mean_area == pytest.approx((100 + 200 + 150) / 3)


def test_merge_gap_splits_into_two_events() -> None:
    agg = EventAggregator(SOURCE, make_params(merge_gap_s=0.5))
    events = feed_all(
        agg,
        [
            (0.0, 100), (0.2, 100), (0.4, 100),
            (2.0, 100), (2.2, 100), (2.4, 100),
        ],
    )
    assert len(events) == 2
    assert events[0].start_s == 0.0 and events[0].end_s == pytest.approx(0.4)
    assert events[1].start_s == pytest.approx(2.0) and events[1].end_s == pytest.approx(2.4)


def test_max_event_duration_force_closes() -> None:
    agg = EventAggregator(
        SOURCE, make_params(merge_gap_s=10.0, max_event_duration_s=1.0)
    )
    events = feed_all(
        agg, [(0.0, 100), (0.5, 100), (1.0, 100), (1.2, 100)]
    )
    assert len(events) == 2
    assert events[0].start_s == 0.0
    assert events[0].end_s == pytest.approx(0.5)
    assert events[1].start_s == pytest.approx(1.0)


def test_cooldown_skips_samples_after_close() -> None:
    agg = EventAggregator(
        SOURCE, make_params(merge_gap_s=0.5, cooldown_s=2.0)
    )
    events = feed_all(
        agg,
        [
            (0.0, 100), (0.4, 100),
            (1.0, 100),
            (1.5, 100),
            (2.5, 100),
        ],
    )
    assert len(events) == 2
    assert events[0].end_s == pytest.approx(0.4)
    assert events[1].start_s == pytest.approx(2.5)


def test_min_motion_frames_drops_event() -> None:
    agg = EventAggregator(
        SOURCE, make_params(merge_gap_s=10.0, min_motion_frames=3)
    )
    events = feed_all(agg, [(0.0, 100), (1.0, 100)])
    assert events == []


def test_min_peak_area_drops_event() -> None:
    agg = EventAggregator(
        SOURCE, make_params(merge_gap_s=10.0, min_peak_area=500)
    )
    events = feed_all(agg, [(0.0, 100), (1.0, 200), (2.0, 150)])
    assert events == []


def test_event_fields_aggregated_correctly() -> None:
    agg = EventAggregator(SOURCE, make_params(merge_gap_s=10.0))
    events = feed_all(agg, [(0.0, 100), (1.0, 300), (2.0, 200)])
    assert len(events) == 1
    ev = events[0]
    assert ev.start_s == 0.0
    assert ev.end_s == pytest.approx(2.0)
    assert ev.duration_s == pytest.approx(2.0)
    assert ev.peak_area == 300
    assert ev.mean_area == pytest.approx(200.0)
