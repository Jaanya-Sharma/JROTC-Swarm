"""Simple contour-based detector for high-contrast objects in video frames."""

from __future__ import annotations

import cv2


Detection = tuple[int, int, int, int, float]


class BlobDetector:
    """Detect bright and dark blobs using two Otsu-thresholded masks."""

    def __init__(
        self,
        min_area: float = 16,
        max_area: float = 80_000,
        nms_iou_threshold: float = 0.4,
        max_detections: int = 80,
    ) -> None:
        self.min_area = min_area
        self.max_area = max_area
        self.nms_iou_threshold = nms_iou_threshold
        self.max_detections = max_detections
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    def detect(self, frame_bgr) -> list[Detection]:
        """Return ``(x1, y1, x2, y2, confidence)`` boxes for a BGR frame."""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        _, dark_mask = cv2.threshold(
            blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        _, bright_mask = cv2.threshold(
            blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        candidates = []
        for mask in (dark_mask, bright_mask):
            opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
            contours, _ = cv2.findContours(
                opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            for contour in contours:
                area = cv2.contourArea(contour)
                if not self.min_area <= area <= self.max_area:
                    continue

                x, y, width, height = cv2.boundingRect(contour)
                # Larger contours are generally more stable; cap the score to 1.
                confidence = min(1.0, area / self.max_area)
                candidates.append((x, y, x + width, y + height, confidence))

        candidates.sort(key=lambda detection: detection[4], reverse=True)
        return self._non_maximum_suppression(candidates)

    def _non_maximum_suppression(
        self, candidates: list[Detection]
    ) -> list[Detection]:
        kept = []
        for candidate in candidates:
            if all(self._iou(candidate, existing) < self.nms_iou_threshold for existing in kept):
                kept.append(candidate)
                if len(kept) == self.max_detections:
                    break
        return kept

    @staticmethod
    def _iou(first: Detection, second: Detection) -> float:
        ax1, ay1, ax2, ay2, _ = first
        bx1, by1, bx2, by2, _ = second

        intersection_width = max(0, min(ax2, bx2) - max(ax1, bx1))
        intersection_height = max(0, min(ay2, by2) - max(ay1, by1))
        intersection = intersection_width * intersection_height
        if intersection == 0:
            return 0.0

        first_area = (ax2 - ax1) * (ay2 - ay1)
        second_area = (bx2 - bx1) * (by2 - by1)
        return intersection / (first_area + second_area - intersection)
