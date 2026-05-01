import pickle

from parking_motion.config import (
    EventParams,
    MotionParams,
    ProcessingParams,
    SessionState,
)


def test_processing_params_pickle_round_trip() -> None:
    params = ProcessingParams(
        frame_skip=7,
        parallel_workers=3,
        motion=MotionParams(
            area_threshold=2000,
            mog_var_threshold=20,
            mog_history=600,
            mog_detect_shadows=False,
            blur_kernel=5,
            morph_kernel=4,
            min_contour_area=10,
        ),
        event=EventParams(
            merge_gap_s=2.5,
            min_duration_s=0.5,
            min_peak_area=100,
            max_event_duration_s=30.0,
            cooldown_s=1.5,
            min_motion_frames=2,
        ),
    )
    restored = pickle.loads(pickle.dumps(params))
    assert restored == params
    assert restored.motion is not params.motion
    assert restored.event is not params.event


def test_default_processing_params_pickle_round_trip() -> None:
    params = ProcessingParams()
    restored = pickle.loads(pickle.dumps(params))
    assert restored == params


def test_session_state_pickle_round_trip() -> None:
    from pathlib import Path

    state = SessionState(
        files=[Path("/tmp/a.mp4"), Path("/tmp/b.mp4")],
        roi=(10, 20, 100, 200),
    )
    restored = pickle.loads(pickle.dumps(state))
    assert restored == state
