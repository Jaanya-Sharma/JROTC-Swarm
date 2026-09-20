"""Geometry predicates for normalized image coordinates."""

from __future__ import annotations


Point = tuple[float, float]
Rect = tuple[float, float, float, float]


def point_in_rect(point: Point, rect: Rect) -> bool:
    """Return whether a point lies inside an axis-aligned rectangle, inclusive."""
    x, y = point
    x1, y1, x2, y2 = rect
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    return left <= x <= right and top <= y <= bottom


def point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    """Return whether a point lies in or on a polygon using ray-casting."""
    if len(polygon) < 3:
        return False

    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if _point_on_segment(point, previous, current):
            return True

        x1, y1 = previous
        x2, y2 = current
        crosses_ray = (y1 > y) != (y2 > y)
        if crosses_ray:
            x_at_y = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_at_y:
                inside = not inside
        previous = current
    return inside


def _point_on_segment(point: Point, start: Point, end: Point) -> bool:
    """Return whether a point lies on the finite segment from start to end."""
    x, y = point
    x1, y1 = start
    x2, y2 = end
    cross_product = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross_product) > 1e-9:
        return False
    return (
        min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9
        and min(y1, y2) - 1e-9 <= y <= max(y1, y2) + 1e-9
    )
