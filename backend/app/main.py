import asyncio
import sqlite3
from itertools import count
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.responses import FileResponse

from app.db import open_database


app = FastAPI(title="Drone Swarm Tracker API")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
VIDEO_PATH = Path(__file__).resolve().parents[1] / "data" / "perdix_swarm_demo.mp4"
MAX_REPLAY_WINDOW_MS = 10 * 60 * 1000
MAX_REPLAY_LIMIT = 20_000
ZONE_IDS = count(1)
ZONES: list[dict] = []
EVENTS: list[dict] = []


class ZoneRect(BaseModel):
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def non_empty(self) -> "ZoneRect":
        if self.x1 >= self.x2 or self.y1 >= self.y2:
            raise ValueError("Zone rectangle must have positive width and height")
        return self


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    rect: ZoneRect

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = "".join(character for character in value.strip() if character >= " " and character != "\x7f")
        if not cleaned:
            raise ValueError("Zone name cannot be empty")
        return cleaned


@app.get("/health")
async def health() -> dict[str, str]:
    """Return a simple liveness response."""
    return {"status": "ok"}


@app.get("/video")
async def video() -> FileResponse:
    """Serve the demo video; FileResponse handles HTTP byte-range requests."""
    if not VIDEO_PATH.is_file():
        raise HTTPException(status_code=404, detail="Demo video not found")
    return FileResponse(VIDEO_PATH, media_type="video/mp4")


@app.get("/replay")
async def replay(
    start_ms: int = Query(ge=0),
    end_ms: int = Query(ge=0),
    limit: int = Query(ge=1, le=MAX_REPLAY_LIMIT),
) -> dict[str, list[dict]]:
    """Return persisted samples for a bounded timestamp range."""
    if start_ms >= end_ms:
        raise HTTPException(status_code=400, detail="start_ms must be less than end_ms")
    if end_ms - start_ms > MAX_REPLAY_WINDOW_MS:
        raise HTTPException(status_code=400, detail="Replay range cannot exceed 10 minutes")

    connection = open_database()
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT ts_ms, track_id, bearing, range_u, heading,
                   rel_speed_u, altitude_m, confidence
            FROM track_samples
            WHERE ts_ms >= ? AND ts_ms <= ?
            ORDER BY ts_ms ASC
            LIMIT ?
            """,
            (start_ms, end_ms, limit),
        ).fetchall()
    finally:
        connection.close()

    return {"samples": [dict(row) for row in rows]}


@app.post("/zones")
async def create_zone(zone: ZoneCreate) -> dict:
    """Create an in-memory zone with normalized rectangle coordinates."""
    created_zone = {"id": next(ZONE_IDS), "name": zone.name, "rect": zone.rect.model_dump()}
    ZONES.append(created_zone)
    return created_zone


@app.get("/events")
async def list_events(
    start_ms: int = Query(ge=0),
    end_ms: int = Query(ge=0),
    limit: int = Query(ge=1, le=MAX_REPLAY_LIMIT),
) -> dict[str, list[dict]]:
    """Return in-memory zone events for a bounded timestamp range."""
    if start_ms >= end_ms:
        raise HTTPException(status_code=400, detail="start_ms must be less than end_ms")
    if end_ms - start_ms > MAX_REPLAY_WINDOW_MS:
        raise HTTPException(status_code=400, detail="Event range cannot exceed 10 minutes")

    events = [
        event for event in EVENTS if start_ms <= event.get("ts_ms", 0) <= end_ms
    ]
    return {"events": events[:limit]}


@app.websocket("/ws/tracks")
async def tracks_websocket(websocket: WebSocket) -> None:
    """Stream a synthetic track snapshot at 10 Hz."""
    await websocket.accept()
    bearing = 0.0

    try:
        while True:
            track = {
                "id": 1,
                "callsign": "UAV-01",
                "type": "multirotor",
                "bearing": bearing,
                "range_u": 0.66,
                "heading": (bearing + 45) % 360,
                "rel_speed_u": 11.0,
                "alt_band": "MED",
                "confidence": 0.85,
                "flags": [],
            }
            await websocket.send_json({"type": "tracks_snapshot", "tracks": [track]})
            bearing = (bearing + 3) % 360
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
