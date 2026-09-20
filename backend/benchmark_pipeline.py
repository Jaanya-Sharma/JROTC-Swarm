"""Benchmark blob and YOLO detection with the same tracking pipeline."""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

from app.detector import BlobDetector
from app.tracker import MultiObjectTracker


DEFAULT_VIDEO = Path(__file__).parent / "data" / "perdix_swarm_demo.mp4"


@dataclass
class RunStats:
    detector: str
    frames: int
    tracks_created: int
    average_track_length_frames: float
    fps: float


def make_detector():
    """Create the detector selected by the ``DETECTOR`` environment variable."""
    detector_name = os.environ["DETECTOR"]
    if detector_name == "blob":
        return BlobDetector()
    if detector_name == "yolo":
        from app.yolo_detector import YoloDetector

        return YoloDetector()
    raise ValueError(f"Unsupported DETECTOR={detector_name!r}; use 'blob' or 'yolo'")


def run_pipeline(
    detector_name: str, video_path: Path, start_sec: float, duration_sec: float
) -> RunStats:
    os.environ["DETECTOR"] = detector_name
    detector = make_detector()
    tracker = MultiObjectTracker()
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        raise RuntimeError("Video does not report a valid frame rate")
    capture.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)
    frame_limit = round(duration_sec * fps)
    track_ages: dict[int, int] = {}
    frames = 0

    started_at = time.perf_counter()
    while frames < frame_limit:
        ok, frame = capture.read()
        if not ok:
            break
        tracks = tracker.update(detector.detect(frame))
        for track in tracks:
            track_ages[track.id] = track.age
        frames += 1
    elapsed = time.perf_counter() - started_at
    capture.release()

    average_track_length = (
        sum(track_ages.values()) / len(track_ages) if track_ages else 0.0
    )
    return RunStats(
        detector=detector_name,
        frames=frames,
        tracks_created=len(track_ages),
        average_track_length_frames=average_track_length,
        fps=frames / elapsed if elapsed else 0.0,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--start-sec", type=float, default=0.0)
    parser.add_argument("--duration-sec", type=float, default=60.0)
    args = parser.parse_args()

    for detector_name in ("blob", "yolo"):
        stats = run_pipeline(
            detector_name, args.video, args.start_sec, args.duration_sec
        )
        print(
            f"DETECTOR={stats.detector}: frames={stats.frames}, "
            f"tracks_created={stats.tracks_created}, "
            f"average_track_length={stats.average_track_length_frames:.1f} frames, "
            f"fps={stats.fps:.2f}"
        )


if __name__ == "__main__":
    main()
