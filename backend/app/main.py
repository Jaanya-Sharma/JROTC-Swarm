import asyncio
import os
import re
import sqlite3
import time
from itertools import count
from math import cos, pi, sin
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.responses import FileResponse, JSONResponse

from app.auth import auth_required, create_access_token, credentials_are_valid, require_http_auth, require_websocket_auth
from app.db import TrackSampleWriter, open_database
from app.pipeline import VideoPipeline
from app.rate_limit import PerIpRateLimiter
from app.zones import ZoneEventEngine


app = FastAPI(title="Drone Swarm Tracker API")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Range"],
    expose_headers=["Accept-Ranges", "Content-Length", "Content-Range"],
)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    if not RATE_LIMITER.allow(client_ip):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def request_validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
    """Return one safe 400 response for invalid query, path, and JSON inputs."""
    messages = [item["msg"] for item in error.errors()]
    return JSONResponse(status_code=400, content={"detail": messages})


VIDEO_PATH = Path(__file__).resolve().parents[1] / "data" / "perdix_swarm_demo.mp4"
MAX_REPLAY_WINDOW_MS = 10 * 60 * 1000
MAX_REPLAY_LIMIT = 20_000
ZONE_IDS = count(1)
ZONES: list[dict] = []
EVENTS: list[dict] = []
RADAR_WIDTH = 680
RADAR_HEIGHT = 520
RADAR_RADIUS = min(RADAR_WIDTH, RADAR_HEIGHT) / 2 - 28
RATE_LIMITER = PerIpRateLimiter(int(os.getenv("RATE_LIMIT_REQUESTS", "120")), float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")))
AUTH_RATE_LIMITER = PerIpRateLimiter(5, 60)


class ZoneRect(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    rect: ZoneRect

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = "".join(character for character in value.strip() if character >= " " and character != "\x7f")
        if not cleaned:
            raise ValueError("Zone name cannot be empty")
        return cleaned


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


def engine_zones() -> list[dict]:
    """Convert API rectangle objects to the tuple form used by the engine."""
    return [
        {
            "id": zone["id"],
            "rect": (
                zone["rect"]["x1"],
                zone["rect"]["y1"],
                zone["rect"]["x2"],
                zone["rect"]["y2"],
            ),
        }
        for zone in ZONES
    ]


def track_radar_position(track: dict) -> tuple[float, float]:
    """Convert a radar bearing/range track to the SVG's normalized coordinates."""
    angle = (track["bearing"] - 90) * pi / 180
    x = RADAR_WIDTH / 2 + RADAR_RADIUS * track["range_u"] * cos(angle)
    y = RADAR_HEIGHT / 2 + RADAR_RADIUS * track["range_u"] * sin(angle)
    return x / RADAR_WIDTH, y / RADAR_HEIGHT


@app.get("/health")
async def health() -> dict[str, bool]:
    """Return a simple liveness response."""
    return {"ok": True}


@app.post("/auth/token")
async def token(credentials: TokenRequest, request: Request) -> dict[str, str]:
    client_ip = request.client.host if request.client else "unknown"
    if not AUTH_RATE_LIMITER.allow(client_ip):
        raise HTTPException(status_code=429, detail="Too many authentication attempts")
    if not auth_required():
        raise HTTPException(status_code=400, detail="Authentication is not enabled")
    if not credentials_are_valid(credentials.username, credentials.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_access_token(credentials.username), "token_type": "bearer"}


def validate_range_header(value: str | None, file_size: int) -> None:
    """Reject malformed or unsatisfiable single-byte ranges before FileResponse."""
    if value is None:
        return
    if len(value) > 256:
        raise HTTPException(status_code=400, detail="Range header is too long")
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if match is None or not any(match.groups()):
        raise HTTPException(status_code=400, detail="Invalid Range header")
    start_text, end_text = match.groups()
    if start_text:
        start = int(start_text)
        if start >= file_size or (end_text and int(end_text) < start):
            raise HTTPException(status_code=400, detail="Range is outside the video")
    elif int(end_text) <= 0:
        raise HTTPException(status_code=400, detail="Range is outside the video")


@app.get("/video")
async def video(request: Request, _: str | None = Depends(require_http_auth)) -> FileResponse:
    """Serve the demo video; FileResponse handles HTTP byte-range requests."""
    if not VIDEO_PATH.is_file():
        raise HTTPException(status_code=404, detail="Demo video not found")
    validate_range_header(request.headers.get("range"), VIDEO_PATH.stat().st_size)
    return FileResponse(VIDEO_PATH, media_type="video/mp4")


@app.get("/replay")
async def replay(
    start_ms: int = Query(ge=0),
    end_ms: int = Query(ge=0),
    limit: int = Query(ge=1, le=MAX_REPLAY_LIMIT),
    _: str | None = Depends(require_http_auth),
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
async def create_zone(zone: ZoneCreate, _: str | None = Depends(require_http_auth)) -> dict:
    """Create an in-memory zone with normalized rectangle coordinates."""
    created_zone = {"id": next(ZONE_IDS), "name": zone.name, "rect": zone.rect.model_dump()}
    ZONES.append(created_zone)
    return created_zone


@app.get("/events")
async def list_events(
    start_ms: int = Query(ge=0),
    end_ms: int = Query(ge=0),
    limit: int = Query(ge=1, le=MAX_REPLAY_LIMIT),
    _: str | None = Depends(require_http_auth),
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
    """Stream tracked video frames, bboxes, and zone events."""
    client_ip = websocket.client.host if websocket.client else "unknown"
    if not RATE_LIMITER.allow(client_ip):
        await websocket.close(code=1013)
        return
    access_token = websocket.query_params.get("access_token")
    if access_token is not None and len(access_token) > 4096:
        # A WebSocket cannot return an HTTP response after upgrade; 1008 is the
        # protocol equivalent for rejected client input.
        await websocket.close(code=1008, reason="access_token is too long")
        return
    if auth_required() and await require_websocket_auth(websocket) is None:
        return
    await websocket.accept()
    pipeline = VideoPipeline(VIDEO_PATH)
    connection = open_database()
    writer = TrackSampleWriter(connection)
    zone_engine = ZoneEventEngine([])
    await websocket.send_json({"type": "hello", "frame_w": pipeline.frame_w, "frame_h": pipeline.frame_h, "fps": pipeline.fps})

    try:
        while True:
            message = pipeline.next_frame()
            if message is None:
                break
            await websocket.send_json(message)
            timestamp_ms = int(time.time() * 1000)
            for track in message["tracks"]:
                writer.add_sample({"ts_ms": timestamp_ms, "track_id": track["id"], "bearing": track["bearing"], "range_u": track["range_u"], "heading": track["heading"], "rel_speed_u": track["rel_speed_u"], "altitude_m": track["altitude_m"], "confidence": track["confidence"]})
            zone_engine.zones = engine_zones()
            zone_updates = []
            for track in message["tracks"]:
                x, y = track_radar_position(track)
                zone_updates.append({"id": track["id"], "x": x, "y": y, "ts_ms": timestamp_ms})
            events = zone_engine.process(
                zone_updates
            )
            if events:
                zone_names = {zone["id"]: zone["name"] for zone in ZONES}
                for event in events:
                    event["zone_name"] = zone_names.get(event["zone_id"], "Unknown zone")
                EVENTS.extend(events)
                if len(EVENTS) > 10_000:
                    del EVENTS[:-10_000]
                await websocket.send_json({"type": "events", "events": events})
            await asyncio.sleep(1 / pipeline.fps)
    except WebSocketDisconnect:
        pass
    except Exception:
        # Do not expose internal processing errors to a connected client.
        await websocket.close(code=1011, reason="Internal server error")
    finally:
        writer.flush()
        connection.close()
        pipeline.close()
