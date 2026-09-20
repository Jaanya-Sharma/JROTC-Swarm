"""YOLOv8 detector adapter with the same interface as ``BlobDetector``."""

from __future__ import annotations

from ultralytics import YOLO


Detection = tuple[int, int, int, int, float]


class YoloDetector:
    """Run the pretrained YOLOv8n model on BGR video frames."""

    def __init__(
        self, model_name: str = "yolov8n.pt", confidence_threshold: float = 0.12
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.model = YOLO(model_name)

    def detect(self, frame_bgr) -> list[Detection]:
        """Return ``(x1, y1, x2, y2, confidence)`` boxes for a BGR frame."""
        result = self.model(
            frame_bgr, conf=self.confidence_threshold, verbose=False
        )[0]
        detections = []
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().tolist()
            confidence = float(box.conf[0].cpu())
            detections.append(
                (round(x1), round(y1), round(x2), round(y2), confidence)
            )
        return sorted(detections, key=lambda detection: detection[4], reverse=True)
