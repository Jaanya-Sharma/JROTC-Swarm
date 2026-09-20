"""Enter, exit, and dwell detection for normalized track positions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from app.geometry import point_in_polygon, point_in_rect


DWELL_TIME_MS = 5_000


@dataclass
class _ZoneState:
    inside: bool = False
    entered_at_ms: int | None = None
    dwell_emitted: bool = False


class ZoneEventEngine:
    """Emit events for tracks entering, exiting, and dwelling in configured zones.

    A zone mapping needs an ``id`` plus either ``rect=(x1, y1, x2, y2)`` or
    ``polygon=[(x, y), ...]``. Each track update needs ``id``, ``x``, ``y``,
    and ``ts_ms``.
    """

    def __init__(self, zones: Iterable[Mapping]) -> None:
        self.zones = list(zones)
        self._states: dict[tuple[int, object], _ZoneState] = {}

    def process(self, track_updates: Iterable[Mapping]) -> list[dict]:
        """Process updates and return any enter, exit, or dwell events."""
        events = []
        for track in track_updates:
            track_id = track["id"]
            point = (track["x"], track["y"])
            timestamp_ms = track["ts_ms"]

            for zone in self.zones:
                zone_id = zone["id"]
                state = self._states.setdefault((track_id, zone_id), _ZoneState())
                is_inside = self._contains(zone, point)

                if is_inside and not state.inside:
                    state.inside = True
                    state.entered_at_ms = timestamp_ms
                    state.dwell_emitted = False
                    events.append(self._event("enter", track_id, zone_id, timestamp_ms))
                elif not is_inside and state.inside:
                    state.inside = False
                    state.entered_at_ms = None
                    state.dwell_emitted = False
                    events.append(self._event("exit", track_id, zone_id, timestamp_ms))
                elif (
                    is_inside
                    and not state.dwell_emitted
                    and timestamp_ms - state.entered_at_ms >= DWELL_TIME_MS
                ):
                    state.dwell_emitted = True
                    events.append(self._event("dwell", track_id, zone_id, timestamp_ms))
        return events

    @staticmethod
    def _contains(zone: Mapping, point: tuple[float, float]) -> bool:
        if "polygon" in zone:
            return point_in_polygon(point, zone["polygon"])
        if "rect" in zone:
            return point_in_rect(point, zone["rect"])
        raise ValueError(f"Zone {zone.get('id')!r} needs a 'polygon' or 'rect'")

    @staticmethod
    def _event(event_type: str, track_id: int, zone_id: object, timestamp_ms: int) -> dict:
        return {
            "type": event_type,
            "track_id": track_id,
            "zone_id": zone_id,
            "ts_ms": timestamp_ms,
        }
