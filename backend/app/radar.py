"""Camera-coordinate conversions for the radar display."""


HORIZONTAL_FOV_DEGREES = 60.0


def pixel_to_radar(
    cx: float, cy: float, frame_w: int, frame_h: int
) -> tuple[float, float]:
    """Map a pixel center to ``(bearing, range_u)`` for a 60° camera FOV.

    The image center is north (0°); the left and right image boundaries map
    to 330° and 30°, respectively.  Range is 1 at the top and 0 at the bottom.
    """
    if frame_w <= 0 or frame_h <= 0:
        raise ValueError("frame_w and frame_h must be positive")

    normalized_x = min(1.0, max(0.0, cx / frame_w))
    normalized_y = min(1.0, max(0.0, cy / frame_h))
    bearing = ((normalized_x - 0.5) * HORIZONTAL_FOV_DEGREES) % 360.0
    range_u = 1.0 - normalized_y
    return bearing, range_u
