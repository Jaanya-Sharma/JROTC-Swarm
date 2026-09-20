import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="Drone Swarm Tracker API")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Return a simple liveness response."""
    return {"status": "ok"}


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
