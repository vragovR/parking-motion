from dataclasses import dataclass

import cv2
import numpy as np

from parking_motion.config import MotionParams


@dataclass
class MotionSample:
    t_seconds: float
    area: int


class RoiMotionDetector:
    def __init__(
        self,
        roi: tuple[int, int, int, int],
        params: MotionParams,
    ) -> None:
        self._x, self._y, self._w, self._h = roi
        self._area_threshold = max(0, params.area_threshold)
        self._blur_kernel = (
            params.blur_kernel
            if params.blur_kernel >= 3 and params.blur_kernel % 2 == 1
            else 0
        )
        self._morph_kernel = max(0, params.morph_kernel)
        self._min_contour_area = max(0, params.min_contour_area)
        self._bg = cv2.createBackgroundSubtractorMOG2(
            history=max(1, params.mog_history),
            varThreshold=max(1, params.mog_var_threshold),
            detectShadows=bool(params.mog_detect_shadows),
        )

    def process(self, frame_bgr: np.ndarray, t_seconds: float) -> MotionSample | None:
        h, w = frame_bgr.shape[:2]
        x = max(0, min(self._x, w))
        y = max(0, min(self._y, h))
        x2 = max(0, min(self._x + self._w, w))
        y2 = max(0, min(self._y + self._h, h))
        if x2 <= x or y2 <= y:
            return None
        crop = frame_bgr[y:y2, x:x2]
        if self._blur_kernel:
            k = self._blur_kernel
            crop = cv2.GaussianBlur(crop, (k, k), 0)
        mask = self._bg.apply(crop)
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        if self._morph_kernel:
            kernel = np.ones((self._morph_kernel, self._morph_kernel), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if self._min_contour_area:
            contours = [c for c in contours if cv2.contourArea(c) >= self._min_contour_area]
        area = int(sum(cv2.contourArea(c) for c in contours))
        if area < self._area_threshold:
            return None
        return MotionSample(t_seconds=t_seconds, area=area)
