"""Video detection, tracking, and WebSocket-frame construction."""

from __future__ import annotations

import math
import os
from pathlib import Path

import cv2

from app.detector import BlobDetector
from app.radar import pixel_to_radar
from app.tracker import MultiObjectTracker


class VideoPipeline:
    def __init__(self, video_path: Path) -> None:
        self.capture = cv2.VideoCapture(str(video_path))
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")
        self.frame_w = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self.capture.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_index = 0
        self.tracker = MultiObjectTracker()
        self.detector = self._make_detector()

    def _make_detector(self):
        if os.getenv("DETECTOR", "blob").lower() == "yolo":
            from app.yolo_detector import YoloDetector

            return YoloDetector()
        return BlobDetector()

    def next_frame(self) -> dict | None:
        ok, frame = self.capture.read()
        if not ok:
            return None
        detections = self.detector.detect(frame)
        tracks = self.tracker.update(detections)
        payload_tracks = []
        for track in tracks:
            bearing, range_u = pixel_to_radar(track.cx, track.cy, self.frame_w, self.frame_h)
            heading = math.degrees(math.atan2(track.vx, -track.vy)) % 360
            payload_tracks.append({
                "id": track.id,
                "callsign": f"UAV-{track.id:02d}",
                "type": "unknown",
                "bearing": bearing,
                "range_u": range_u,
                "heading": heading,
                "rel_speed_u": min(30.0, math.hypot(track.vx, track.vy) / 10),
                "alt_band": "MED",
                "altitude_m": None,
                "confidence": track.confidence,
                "flags": [],
            })
        message = {
            "type": "tracks_snapshot",
            "media_t_sec": self.frame_index / self.fps,
            "frame_w": self.frame_w,
            "frame_h": self.frame_h,
            "tracks": payload_tracks,
            "bboxes": detections,
        }
        self.frame_index += 1
        return message

    def close(self) -> None:
        self.capture.release()
