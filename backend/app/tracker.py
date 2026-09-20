"""A lightweight IoU and centroid-distance multi-object tracker."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot


Detection = tuple[int, int, int, int, float]


@dataclass
class Track:
    id: int
    cx: float
    cy: float
    vx: float
    vy: float
    age: int
    misses: int
    bbox: tuple[int, int, int, int]
    confidence: float


class MultiObjectTracker:
    """Maintain stable IDs using IoU first and centroid distance as a fallback."""

    def __init__(
        self,
        iou_threshold: float = 0.1,
        distance_threshold: float = 80.0,
        max_misses: int = 20,
        velocity_alpha: float = 0.35,
    ) -> None:
        self.iou_threshold = iou_threshold
        self.distance_threshold = distance_threshold
        self.max_misses = max_misses
        self.velocity_alpha = velocity_alpha
        self._next_id = 1
        self.tracks: list[Track] = []

    def update(self, detections: list[Detection]) -> list[Track]:
        """Associate detections with tracks and return the active tracks."""
        matches = self._match_detections(detections)
        matched_track_indices = {track_index for track_index, _ in matches}
        matched_detection_indices = {detection_index for _, detection_index in matches}

        for track_index, detection_index in matches:
            self._update_track(self.tracks[track_index], detections[detection_index])

        for track_index, track in enumerate(self.tracks):
            if track_index not in matched_track_indices:
                track.age += 1
                track.misses += 1

        self.tracks = [track for track in self.tracks if track.misses <= self.max_misses]

        for detection_index, detection in enumerate(detections):
            if detection_index not in matched_detection_indices:
                self.tracks.append(self._new_track(detection))

        return list(self.tracks)

    def _match_detections(self, detections: list[Detection]) -> list[tuple[int, int]]:
        """Greedily choose one-to-one matches, prioritizing IoU over distance."""
        candidates = []
        for track_index, track in enumerate(self.tracks):
            for detection_index, detection in enumerate(detections):
                iou = self._iou(track.bbox, detection[:4])
                if iou >= self.iou_threshold:
                    # IoU matches always rank above centroid-distance fallbacks.
                    candidates.append((1, iou, track_index, detection_index))
                    continue

                cx, cy = self._center(detection[:4])
                distance = hypot(cx - track.cx, cy - track.cy)
                if distance <= self.distance_threshold:
                    candidates.append((0, -distance, track_index, detection_index))

        candidates.sort(reverse=True)
        matched_tracks = set()
        matched_detections = set()
        matches = []
        for _, _, track_index, detection_index in candidates:
            if track_index in matched_tracks or detection_index in matched_detections:
                continue
            matched_tracks.add(track_index)
            matched_detections.add(detection_index)
            matches.append((track_index, detection_index))
        return matches

    def _new_track(self, detection: Detection) -> Track:
        x1, y1, x2, y2, confidence = detection
        cx, cy = self._center((x1, y1, x2, y2))
        track = Track(
            id=self._next_id,
            cx=cx,
            cy=cy,
            vx=0.0,
            vy=0.0,
            age=1,
            misses=0,
            bbox=(x1, y1, x2, y2),
            confidence=confidence,
        )
        self._next_id += 1
        return track

    def _update_track(self, track: Track, detection: Detection) -> None:
        x1, y1, x2, y2, confidence = detection
        cx, cy = self._center((x1, y1, x2, y2))
        raw_vx = cx - track.cx
        raw_vy = cy - track.cy
        alpha = self.velocity_alpha

        track.vx = alpha * raw_vx + (1 - alpha) * track.vx
        track.vy = alpha * raw_vy + (1 - alpha) * track.vy
        track.cx = cx
        track.cy = cy
        track.age += 1
        track.misses = 0
        track.bbox = (x1, y1, x2, y2)
        track.confidence = confidence

    @staticmethod
    def _center(box: tuple[int, int, int, int]) -> tuple[float, float]:
        x1, y1, x2, y2 = box
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    @staticmethod
    def _iou(
        first: tuple[int, int, int, int], second: tuple[int, int, int, int]
    ) -> float:
        ax1, ay1, ax2, ay2 = first
        bx1, by1, bx2, by2 = second
        intersection_width = max(0, min(ax2, bx2) - max(ax1, bx1))
        intersection_height = max(0, min(ay2, by2) - max(ay1, by1))
        intersection = intersection_width * intersection_height
        if intersection == 0:
            return 0.0

        first_area = (ax2 - ax1) * (ay2 - ay1)
        second_area = (bx2 - bx1) * (by2 - by1)
        return intersection / (first_area + second_area - intersection)
