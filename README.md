# Drone Swarm Tracker

A React tactical-radar interface backed by FastAPI. The backend reads the
Perdix MP4, detects and tracks objects, maps them to radar coordinates, streams
timestamped track snapshots over WebSocket, and records track samples in
SQLite. The UI shows the video with bounding boxes, a synchronized radar,
zones/events, commander notes, and a downloadable After-Action Report (AAR)
PDF.

This is a local development/demo project. See [THREAT_MODEL.md](THREAT_MODEL.md)
for its security assumptions and remaining risks, and
[INSTRUCTIONS.md](INSTRUCTIONS.md) for the original weekly assignment guide.

## Implemented work

| Assignment week | Implemented result |
| --- | --- |
| Week 20 — backend and live radar | FastAPI health endpoint, localhost-only CORS, `/ws/tracks`, and a 72-track simulator fallback when the backend is unavailable. |
| Week 21 — video pipeline | OpenCV MP4 reading, Otsu-based `BlobDetector`, IoU/centroid/EMA `MultiObjectTracker`, and pixel-to-radar mapping. |
| Week 22 — video and detection | Range-enabled `/video`, synchronized HTML video/canvas bbox overlay/radar, playback controls, a selectable `blob` or `yolo` detector, vectors, and simple altitude fields. |
| Week 23 — replay and notes | WAL-mode SQLite track storage, buffered batched writes, bounded `/replay`, and browser `localStorage` commander notes. |
| Week 24 — zones and AAR | SVG draw-zone control, rectangle containment, enter/exit/dwell event engine, WebSocket event messages and event log, and client-side AAR PDF export with a timeline and zone map. |
| Secure-coding final pass | JWT support, per-IP rate limiting, strict request validation, parameterized SQL, CORS allowlist, pinned direct dependencies, ignored `.env`, and this threat model. |

## Prerequisites

- Node.js 20.19+ (required by the installed Vite version)
- Python 3.11+
- The Perdix video at `backend/data/perdix_swarm_demo.mp4`

The repository already contains `backend/yolov8n.pt`. YOLO also requires the
installed Ultralytics/PyTorch dependencies and is slower than the blob detector
on a CPU.

## Configuration

Create a private backend configuration file from the tracked template:

```powershell
cd backend
Copy-Item .env.example .env
```

`backend/.env` is ignored by Git and is loaded automatically when the backend
starts. Configure these values:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AUTH_REQUIRED` | `false` | Enables JWT protection for `/video`, `/replay`, `/zones`, `/events`, and `/ws/tracks`. |
| `JWT_SECRET` | placeholder | Long, random JWT signing secret when authentication is enabled. |
| `API_USERNAME` / `API_PASSWORD` | placeholders | Credentials accepted by `POST /auth/token`. |
| `JWT_EXPIRES_MINUTES` | `60` | JWT lifetime. |
| `DETECTOR` | `blob` | Choose `blob` or `yolo`. |
| `RATE_LIMIT_REQUESTS` | `120` | Maximum HTTP/WebSocket connection attempts per IP per window. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window length. |

Do not commit `.env`, and replace all placeholder credentials before enabling
authentication.

> **Current UI authentication note:** `App.jsx` does not yet acquire or attach
> a JWT. To run the browser UI end-to-end, leave `AUTH_REQUIRED=false`. With it
> set to `true`, protected API calls and the video/WebSocket require a bearer
> token; use the API manually or add a login/token flow to the frontend first.

## Run the application

Use two terminals from the repository root.

### 1. Start the backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://127.0.0.1:8000`. Confirm it with:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response:

```json
{"ok": true}
```

### 2. Start the frontend

```powershell
npm install
npm run dev
```

Open the Vite URL shown in the terminal, normally `http://localhost:5173`.
The app connects to the backend at `127.0.0.1:8000`. If the backend is stopped,
the radar intentionally falls back to the 72 simulated tracks.

### Optional: use JWT-protected API calls

After setting `AUTH_REQUIRED=true` and choosing real credentials in `.env`, get
a token from PowerShell:

```powershell
$body = @{ username = "operator"; password = "your-password" } | ConvertTo-Json
$token = (Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/auth/token -ContentType "application/json" -Body $body).access_token
$uri = 'http://127.0.0.1:8000/replay?start_ms=0&end_ms=1&limit=1'
Invoke-RestMethod -Uri $uri -Headers @{ Authorization = "Bearer $token" }
```

For a WebSocket client, supply the same token as `?access_token=<token>` or as
an `Authorization: Bearer <token>` header. Keep tokens out of screenshots,
shell history, and source files.

## API and stream summary

| Interface | Purpose |
| --- | --- |
| `GET /health` | Liveness response. |
| `POST /auth/token` | Creates a JWT when authentication is enabled. |
| `GET /video` | MP4 with byte-range seeking support. |
| `GET /replay?start_ms=&end_ms=&limit=` | Returns bounded persisted track samples. |
| `POST /zones` | Adds a normalized rectangle zone: `{ "name", "rect": { "x1", "y1", "x2", "y2" } }`. |
| `GET /events?start_ms=&end_ms=&limit=` | Returns recent in-memory zone events. |
| `WS /ws/tracks` | Sends `hello`, timestamped `tracks_snapshot` messages, and zone `events` messages. |

Request schemas reject invalid/out-of-range REST input with HTTP `400`. Invalid
WebSocket policy/auth input is rejected using WebSocket close code `1008`.

## Data behavior and limitations

- Track samples persist to `backend/data/radar.db` while a `/ws/tracks` client
  is connected. SQLite uses WAL mode and batched writes.
- Zones and events are currently in memory. They reset with a backend restart.
- The AAR PDF fetches the last five minutes of `/replay` and `/events`; run the
  backend and allow tracks/events to accumulate before exporting.
- Browser notes are stored locally per track ID and survive page refreshes in
  that browser profile.

## Validation and maintenance

```powershell
# Backend syntax check
backend\.venv\Scripts\python.exe -m compileall -q backend\app

# Frontend production build
npm run build

# Dependency checks
backend\.venv\Scripts\python.exe -m pip list --outdated
npm audit
```

Direct dependencies are pinned in `backend/requirements.txt` and `package.json`.
Review non-critical transitive updates during routine maintenance; apply any
critical security updates promptly.
