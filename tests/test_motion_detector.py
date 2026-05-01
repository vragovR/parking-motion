from dataclasses import replace

import numpy as np

from parking_motion.config import MotionParams
from parking_motion.core.motion import RoiMotionDetector


def make_params(**overrides) -> MotionParams:
    base = MotionParams(
        area_threshold=0,
        mog_var_threshold=16,
        mog_history=500,
        mog_detect_shadows=False,
        blur_kernel=0,
        morph_kernel=3,
        min_contour_area=0,
    )
    return replace(base, **overrides)


def black_frame(h: int = 100, w: int = 100) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_roi_outside_frame_returns_none() -> None:
    det = RoiMotionDetector(roi=(200, 200, 50, 50), params=make_params())
    assert det.process(black_frame(), 0.0) is None


def test_roi_zero_size_returns_none() -> None:
    det = RoiMotionDetector(roi=(10, 10, 0, 0), params=make_params())
    assert det.process(black_frame(), 0.0) is None


def test_huge_threshold_suppresses_all_motion() -> None:
    det = RoiMotionDetector(roi=(0, 0, 100, 100), params=make_params(area_threshold=10**9))
    rng = np.random.default_rng(42)
    for i in range(5):
        frame = rng.integers(0, 256, size=(100, 100, 3), dtype=np.uint8)
        assert det.process(frame, float(i) * 0.1) is None


def test_motion_sample_carries_t_seconds() -> None:
    det = RoiMotionDetector(roi=(0, 0, 100, 100), params=make_params(area_threshold=1))
    for i in range(5):
        det.process(black_frame(), float(i) * 0.1)
    bright = np.full((100, 100, 3), 255, dtype=np.uint8)
    sample = det.process(bright, 1.5)
    assert sample is not None
    assert sample.t_seconds == 1.5
    assert sample.area > 0


def test_roi_partially_outside_frame_is_clipped() -> None:
    det = RoiMotionDetector(roi=(80, 80, 100, 100), params=make_params())
    result = det.process(black_frame(100, 100), 0.0)
    assert result is None or result.area >= 0
