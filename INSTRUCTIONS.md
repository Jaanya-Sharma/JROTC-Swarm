# Drone Swarm Tracker — Project Instructions

You have been given a working React UI that simulates a tactical drone radar. Your job, over four to five weeks, is to replace the simulator with a real Python backend that ingests video, detects and tracks drones, and streams the results to the UI. Focus on using generative AI as your primary development partner and writing the code securely.

## Roadmap

- **Week 20** — Stand up a Python backend and stream one track to the radar from your own server.
- **Week 21** — Open the Perdix demo video, detect and track drones, and feed real blips to the radar.
- **Week 22** — Play the video inside the UI with overlaid bounding boxes; swap your simple detector for a real ML model and compare; add heading vectors and altitude estimates.
- **Week 23** — Persist tracks to a database, replay them on a timeline, and save commander notes that survive a refresh.
- **Week 24** — Add zones, enter/exit/dwell events, and an After-Action Report export.

The UI is yours. Restyle it, rearrange panels, rename buttons — anything you want, as long as the radar keeps consuming the same track data fields. Treat `App.jsx` as a starting point, not a constraint.

## How to use this guide

Each week is structured the same way:

- **What you're building** — plain-language description of the goal and the standard tool to use.
- **Demo** — what a passing submission looks like.
- **Milestones** — three to six small steps inside the week. Each one should run and produce something visible before you move on.
- **Prompting** — example prompts for your AI assistant. Treat them as starting points, not scripts.
- **Verify** — a specific check that proves the milestone works.
- **Secure-coding check** — one concrete concern that ties into the course's security theme.
- **Done when** — short acceptance checklist.

You will hit walls and technical confusion. When the AI gives you something that does not work, do not paste a longer prompt and hope. Understand the code it gave you, identify the logic that is wrong, and ask a narrower question.

Remember, AI is your friend, if something is unclear or you forget something like how to set up a private github repo, how to make a directory in cursor, etc. Consult with your AI coding assistant. And you can utilize other AI tools like chatbots (ChatGPT, Claude, etc.) to explain technical concepts you don't quite understand. This saves context and tokens in your AI coding assistant (Cursor/Gemini, Claude Code, etc.)

---

## Setup

### 1. Install prerequisites

- Node.js 18 or later (`node --version`).
- Python 3.11 or later (`python3 --version`).
- Git (`git --version`).
- A code editor (VS Code is fine).

### 2. Get the starter UI running

```bash
unzip drone-swarm-tracker-2026.zip
cd drone-swarm-tracker-2026
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`). You should see the simulated radar with about 72 fake drones moving. If you do not, fix that before continuing.

### 3. Set up a Python virtual environment

You will need Python from Week 20 onward. Create a virtual environment now so all the Python packages you install stay isolated from your system Python. Make a `backend/` directory at the same level as `src/`:

```bash
mkdir backend
cd backend
python3 -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows PowerShell
```

Your terminal prompt should now show `(.venv)`. Any `pip install` you run from now on goes into this environment and stays there. The `.gitignore` already excludes `.venv/` so it will not get committed. Re-activate it every time you open a new terminal.

### 4. Put the project under version control

```bash
cd ..    # back to the project root
git init
git add .
git commit -m "Initial starter from instructor"
```

Create a private repository on GitHub, then push:

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

Commit at the end of every working session. Open a pull request for each week's work describing your changes before merging into `main`.

### 5. Choose an AI assistant

You've been using Cursor and Gemini in class — those are good defaults for this project. If you want to experience a different tool, both OpenAI's Codex CLI and Anthropic's Claude Code give you direct control of the terminal and your files. Pick one and stay with it; switching mid-project usually wastes time re-explaining context.

### 6. AI workflow primer

- Give context. Paste the relevant file (or the relevant function) and describe the goal. "Help me write a FastAPI server" is bad. "Here is my `app/main.py`. Help me add a WebSocket endpoint at `/ws/tracks` that sends a JSON message every 100 ms" is good.
- Ask for small pieces. If the AI generates more than 100 lines of code at once, you are probably going to find a bug you cannot diagnose. Ask for one function at a time.
- Verify before pasting. Read every line. Run it. If it imports a package, confirm the package is real and is the one you want.
- Never share secrets. API keys, passwords, internal URLs, classmate names, anything sensitive. Treat the chat window like an open Slack channel.
- Push back when the AI overcomplicates. "Simpler" and "no Docker, no extra dependencies" are valid responses.

### 7. Read the existing code

Before writing any backend code, prompt your AI assistant to walk you through `src/App.jsx`. Ask specifically: *"What fields does each fake track have, and what does the radar do with each field?"* The answer is your backend's output contract.

For reference, here is the exact shape `makeTrack()` produces today — your backend should emit objects with these same keys and value ranges so the UI works without any changes:

```js
{
  id: 1,                       // integer, stable per track
  callsign: "UAV-01",          // short label shown on the radar and table
  type: "unknown",             // "multirotor" | "fixedwing" | "unknown"
  bearing: 217.0,              // degrees, 0–360
  range_u: 0.66,               // normalized 0–1 (0 = at camera, 1 = at radar edge)
  heading: 306.0,              // degrees, 0–360
  rel_speed_u: 11.0,           // relative speed roughly 0–30 (rendered as "u/s")
  alt_band: "MED",             // "LOW" | "MED" | "HIGH"
  confidence: 0.58,            // 0–1
  flags: []                    // any of "LOW_CONF", "OCCLUDED", "LOST"
}
```

You can rename any of these fields, but if you do, update `App.jsx` to match. Later weeks will add `bbox` (for drawing on the video) and `altitude_m` (a meters estimate alongside `alt_band`).

---

## Week 20 — Hello from your own backend

**What you're building.** A small Python program that runs in the background and pushes drone data to the browser as it changes. In web-dev terms this is a "backend server with a WebSocket." Use **FastAPI** (a Python library for building small web servers) and **uvicorn** (the program that actually runs your server). When this week is done, the radar in the UI will receive live updates from your code instead of from the built-in simulator.

**Demo.** A single track moves on the radar, but the data is coming from a Python server you wrote — not from the simulator.

**Milestones:**

1. Inside `backend/`, install the libraries you need: `pip install fastapi 'uvicorn[standard]'`. Create `backend/app/main.py` with a single health endpoint at `GET /health` that returns `{"ok": true}`. Run it with `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` (from inside `backend/`). Visit `http://127.0.0.1:8000/health` and confirm the JSON.
2. Add a WebSocket endpoint at `/ws/tracks` that accepts a connection and sends one greeting message `{"type": "hello", "frame_w": 1024, "frame_h": 576, "fps": 30}` as soon as a client connects.
3. In the same WebSocket loop, send a `tracks_snapshot` message every 100 ms with one fake track whose `bearing` slowly rotates around the radar. Use the field shape documented in Setup step 7.
4. Configure CORS on the FastAPI app so the browser can talk to it. Vite usually runs on `http://localhost:5173`, but it falls back to 5174, 5175, and so on when other things hold those ports. A localhost-only regex covers all of them: `allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$"`.
5. In `App.jsx`, define a `BACKEND_WS_URL` constant at the top of the file (for example `'ws://127.0.0.1:8000/ws/tracks'`) so it is easy to change later. Add a `useState` for the latest WebSocket tracks (start as `null`) and a `useEffect` that opens the connection, parses each incoming JSON message, and stores the `tracks_snapshot` payload. In the existing `useMemo` that builds the 72 simulated tracks, return the WebSocket tracks when they are non-null; otherwise fall back to the simulator. The page then renders the simulator until the backend connects, then swaps to live data.

**Prompting:**

- *"Help me create a minimal FastAPI app at `backend/app/main.py` with one health endpoint and one WebSocket at `/ws/tracks`. No database, no auth, no Docker. I want to run it with `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` from inside `backend/`."*
- *"Inside the WebSocket loop, send a `tracks_snapshot` every 100 ms with one track whose `bearing` rotates around the radar. The track shape must match what the UI already consumes (see the table in Setup step 7): `{id, callsign, type, bearing, range_u, heading, rel_speed_u, alt_band, confidence, flags}`. Use `asyncio.sleep(0.1)`."*
- *"Add CORS to my FastAPI app using a regex that allows any localhost port: `allow_origin_regex=r'^http://(localhost|127\.0\.0\.1):\\d+$'`. This way Vite can pick 5174 or 5175 if 5173 is taken and CORS still works."*
- *"Here is my `App.jsx`. At the top of the file add a `BACKEND_WS_URL` constant. Inside the component, add a state variable `wsTracks` (default null) and a `useEffect` that opens the WebSocket, parses each `tracks_snapshot` message, and updates the state. Change the existing `useMemo` so it returns `wsTracks` when non-null, otherwise builds the simulated tracks. Keep the simulator intact as a fallback."*
- If the AI suggests Flask, Django, or a docker-compose file: *"Stick to FastAPI in a single Python file. No containers, no extra services."*

**Verify:**

- `curl http://127.0.0.1:8000/health` returns `{"ok": true}`.
- With the backend stopped, the radar in the browser still renders 72 simulated tracks (the fallback works).
- Start the backend, refresh the page. Open the browser's developer tools, Network tab, WS filter. You see the connection upgrade to 101 and a `tracks_snapshot` frame every 100 ms.
- The radar drops down to a single blip rotating slowly. That blip is yours.

**Secure-coding check.** Bind your dev server to `127.0.0.1`, not `0.0.0.0`. A server bound to `0.0.0.0` on a shared network is reachable by anyone else on it. Run `uvicorn ... --host 127.0.0.1 ...` explicitly rather than relying on defaults.

**Done when:**

- [ ] Backend runs with `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` from inside `backend/`.
- [ ] With the backend off, the page falls back to the 72-track simulator.
- [ ] With the backend on, the radar shows one rotating track from your server.
- [ ] The browser dev tools show the WebSocket frames in real time.

---

## Week 21 — Real drones from video

**What you're building.** A pipeline that reads each frame of the demo video, finds the drone-shaped things in it, assigns each one a stable identity it keeps across frames, and reports their positions to the radar. Use **OpenCV** (`pip install opencv-python`) for the video and image work, and write a small Python class of your own for the tracker.

The video is a 3 minute 31 second clip from a 2016 Navy test at China Lake. Original page on DVIDS: `https://www.dvidshub.net/video/504622/perdix-swarm-demo-oct-2016`. A mirror is on Google Drive at `https://drive.google.com/file/d/1xaQcSnWxDr21sfaU8R_0tf02zzRzYd0C/view`. Download it, rename it to `perdix_swarm_demo.mp4`, and put it at `backend/data/perdix_swarm_demo.mp4`. The mirror is 1280×720 at 29.97 fps; do not hardcode dimensions in your code — read them from the file with `cap.get(cv2.CAP_PROP_FRAME_WIDTH)` etc.

**Demo.** The Perdix video is processed frame by frame, and the things it sees show up as moving blips on the radar.

Heads up about this video before you start: it is not a single clean clip of drones in the sky. It cuts between three kinds of footage:
- Two F/A-18 launch aircraft flying against bright sky (early in the clip).
- Tiny Perdix drones falling out of those jets (small, fast, hard).
- A synthetic tactical screen recording showing a satellite map with drone icons moving on it (later in the clip).

For this week, "drone" is whatever your detector finds — the jets, the icons, and any small specks against the sky. That is fine. Week 22 introduces a real ML detector (YOLOv8) that will improve quality on the hard cases.

**Milestones:**

1. Open the video with OpenCV (`cv2.VideoCapture`) and print the resolution and total frame count. Read the first frame and save it to disk as a sanity check.
2. Write a `BlobDetector` class with a `detect(frame_bgr)` method that returns a list of `(x1, y1, x2, y2, confidence)` boxes. Use Otsu thresholding twice — once on the inverted grayscale (catches dark targets like aircraft against bright sky) and once on the non-inverted (catches bright targets like icons or specular highlights). Merge the two sets with a simple non-maximum suppression. Filter contours by area: start with `min_area = 16` (smaller produces noise the tracker cannot lock onto) and a generous `max_area` (around 80000) so that both big jets and tiny specks are accepted. Save a debug image with the boxes drawn so you can see what your detector is finding.
3. Write a `MultiObjectTracker` that assigns stable integer IDs across frames. Match new detections to existing tracks by IoU **with a centroid-distance fallback** — IoU alone fails on small boxes that move more than their own size between frames. Use roughly `iou_thresh = 0.1`, `dist_thresh ≈ 80 px`, and `max_misses ≈ 20` (about 2/3 of a second at 30 fps). Unmatched detections start new tracks; tracks past the miss limit get dropped. Each track records its center, velocity (EMA-smoothed), age, and confidence.
4. Write a `pixel_to_radar(cx, cy, frame_w, frame_h)` function that returns `(bearing, range_u)`. Bearing comes from the horizontal pixel offset and a fixed 60° horizontal FOV. Range is the vertical position normalized to `[0, 1]` (top = far, bottom = near).
5. Replace the single hardcoded track from Week 20 with a live stream of all detected and tracked drones over the same WebSocket. Read `frame_w`, `frame_h`, and `fps` from `cv2.VideoCapture` rather than hardcoding them — they vary between source files. The radar should now show many moving blips. Track count will rise and fall as the video transitions between scenes; that is expected.

**Prompting:**

- *"Write a Python class `BlobDetector` with `detect(frame_bgr) -> [(x1, y1, x2, y2, conf), ...]`. Convert to grayscale, Gaussian-blur (5×5), then run Otsu thresholding twice — once on the inverted image (dark targets become foreground) and once on the non-inverted image (bright targets). Apply a 3×3 morphological open to each mask, extract external contours, filter by area (min 16 px², max 80000 px²), then merge the two sets with non-maximum suppression at IoU 0.4. Return at most 80 boxes ordered by confidence."*
- *"Write a `MultiObjectTracker` that keeps active tracks with `id, cx, cy, vx, vy, age, misses`. On each frame, score every candidate match: prefer matches with IoU ≥ 0.1, but fall back to centroid distance within roughly 80 pixels when IoU fails (which it often does for small boxes). Velocity is an EMA of per-frame center deltas. Drop tracks after about 20 misses."*
- If the AI suggests DeepSORT, ByteTrack, or training a model: *"No ML model and no extra trackers. Pure Python IoU + centroid distance + EMA velocity."*
- *"Camera FOV is 60° horizontal. Write `pixel_to_radar(cx, cy, frame_w, frame_h)` so that the frame center maps to bearing 0° (north on the radar), the right edge to about +30°, the left edge to about 330°, and range_u falls from 1 at the top of the frame to 0 at the bottom."*

**Verify:**

- The saved debug image shows boxes around drone-shaped contours.
- Print track count per frame. It should rise quickly, then stabilize. If it grows without bound, your tracker is failing to match.
- Watching the video and the radar side by side, track motion on the radar should match drone motion on the screen.

**Secure-coding check.** If you accept the video path from an environment variable or query parameter, validate it. Resolve it to an absolute path and confirm it sits inside an expected directory. A path like `../../../etc/passwd` should be rejected before `cv2.VideoCapture` sees it.

**Done when:**

- [ ] Backend opens the Perdix MP4 and reports its resolution and frame count.
- [ ] Your detector and tracker produce at least three IDs that survive for two seconds or more on the demo clip (this is the bar; in practice you will see dozens).
- [ ] The radar shows real tracks derived from the video instead of the simulator.
- [ ] Track count rises and falls as the video transitions between aerial footage and the tactical-screen sections — that variation is expected.

---

## Week 22 — Video panel, real detection model, vectors, altitude

**What you're building.** Until now the radar has been the only window into your system. This week the user can also watch the original video with the detector's bounding boxes drawn on it, which makes detection quality obvious. With that visual feedback in place, you'll swap your simple detector for a real machine-learning model (**YOLOv8**, via the `ultralytics` library) and write a short comparison. You'll also produce three numbers per drone that the radar needs but does not yet have: `heading`, `rel_speed_u`, and `altitude_m`. Heading and speed come from the tracker's velocity. Altitude is estimated from one or more known landmarks in the scene.

**Demo.** The video plays in the left panel of the UI with live bounding boxes overlaid. The radar follows the video — pause the video and the radar pauses; seek backward and the radar rewinds with it. Heading vectors point the right direction. The inspector shows a real altitude in meters for each track. You can switch between the blob detector and YOLOv8 with a single environment variable, and you have a short writeup comparing the two.

**Milestones:**

1. **Serve the video.** Add `GET /video` to the backend that serves the MP4 with HTTP Range request support, so the browser's `<video>` element can seek. FastAPI's `FileResponse` plus `Accept-Ranges: bytes` is enough.
2. **Play it in the UI.** Replace the video placeholder in `App.jsx` with a `<video>` element pointing at `http://127.0.0.1:8000/video`. Confirm it plays and seeks.
3. **Overlay bounding boxes.** Layer a `<canvas>` on top of the video. Maintain a sliding buffer of recent WebSocket frames keyed by `media_t_sec` (frame index ÷ FPS). On every `requestAnimationFrame`, read `video.currentTime`, find the closest buffered frame, and draw its boxes onto the canvas.
4. **Swap in YOLOv8 and compare.** Install `ultralytics` (`pip install ultralytics`) and write a `YoloDetector` with the same `detect(frame)` signature as `BlobDetector`. Load `yolov8n.pt` (the smallest YOLOv8 model — `ultralytics` downloads it the first time or you can drop the file in `backend/data/`). Make the detector selectable with an environment variable like `DETECTOR=blob` or `DETECTOR=yolo`. Then run each detector on the same short slice of the Perdix clip and write a short comparison (a markdown file in your repo is fine): which detector finds more drones, what each gets wrong, and how the FPS compares on your machine. Eyeball judgment is fine — no precision/recall numbers needed. **Important:** YOLOv8n on a typical CPU runs under 1 fps at the default image size. Use a 3–5 second slice (around 90–150 frames), not 60 seconds, or you will sit waiting for 20+ minutes. If your laptop has a GPU and you want to use it, ultralytics picks it up automatically.
5. **Heading and speed.** From the tracker's velocity `(vx, vy)` in pixels per second, compute `heading = degrees(atan2(vx, -vy))` mapped to `[0, 360)`, and `rel_speed_u = sqrt(vx² + vy²) / NORM`. Pick `NORM` so `rel_speed_u` sits roughly in the 0–30 range the UI expects (the vector length formula in `App.jsx` is `18 + rel_speed_u * 0.7`). Start with `NORM = 10` and adjust until the vectors look proportional. Include both in every track payload, toggle "Vectors" on in the UI, and confirm the arrows point where you expect.
6. **Altitude from landmarks.** Pick a stationary feature visible in the demo clip (a mountain ridge, a building rooftop, a hard horizon line) and write a small JSON config file with: the camera's latitude, longitude, and approximate height above ground; the vertical FOV; and one or more reference points (pixel position in the frame + real-world elevation in meters). Derive a function that maps `pixel_y` to an elevation angle above the horizon. For each tracked drone, combine that angle with the existing range estimate to produce `altitude_m`. Add `altitude_m` to the track payload and surface it in the inspector.

7. **Lock the radar to the video timeline.** Your bbox overlay already tracks `video.currentTime` — every animation frame it finds the closest buffered WS snapshot. The radar does not, so pausing or seeking the video desynchronizes the two views. Fix it: extend your sliding WS buffer to roughly 60 seconds, run the same closest-frame lookup on every animation frame, and push the result into a state the radar consumes. Now play, pause, and seek on the `<video>` element all control what the radar shows. If the video is seeked further back than your buffer holds, fall back to the closest frame you do have (the radar will look stale, which is the right signal to the user).

**Prompting:**

- *"Add `GET /video` to my FastAPI app that serves an MP4 with HTTP Range support so Chrome and Safari can seek the `<video>` element. Use `starlette.responses.FileResponse` if it handles ranges; otherwise write a manual range handler. Keep it short."*
- *"My WebSocket sends frames with `media_t_sec` and a list of bboxes. Add a React canvas overlay on top of the `<video>` element. Use `requestAnimationFrame` to read `video.currentTime`, find the closest buffered WS frame, and draw the boxes."*
- *"Wrap `ultralytics.YOLO('yolov8n.pt')` in a `YoloDetector` class with the same `detect(frame_bgr) -> [(x1, y1, x2, y2, conf), ...]` signature as my `BlobDetector`. Lower the confidence threshold to 0.12 because drones in this clip are very small."*
- *"Help me write a script that runs my pipeline twice — once with `DETECTOR=blob`, once with `DETECTOR=yolo` — on a 60-second slice of `perdix_swarm_demo.mp4`. Count tracks created, average track length, and approximate FPS. Print the results."*
- *"Derive a small-angle formula that maps a pixel's vertical offset from the optical center to an elevation angle above the horizon, given a vertical FOV of V degrees and a frame height of H pixels. Then, given a landmark at known pixel position and known real-world elevation, and the camera's lat/lon and height, solve for an altitude estimate for any other point in the frame."*
- *"My bbox canvas already finds the closest buffered WS frame to `video.currentTime`. Pull that same lookup out into a state value (call it `syncedTracks`) and feed it to the radar instead of the latest WS snapshot. Extend the sliding buffer to about 60 seconds so seeks backward still have data."*
- If the AI tries to fine-tune YOLO, build a full camera calibration with chessboards, or pull in PyTorch from source: *"Use pretrained `yolov8n.pt` as-is and stick to simple arithmetic for altitude."*

**Verify:**

- The video plays inside the UI, served by your backend. The Network tab shows `/video` requests.
- Boxes drawn on the canvas approximately track moving drones in the video.
- `DETECTOR=yolo uvicorn app.main:app ...` runs end-to-end and produces tracks. `DETECTOR=blob` gives different output. Your comparison writeup is committed to the repo with at least one specific observation per detector.
- Vector arrows on the radar correlate with on-screen drone motion.
- The inspector shows `altitude_m` for each track, the numbers do not jump wildly between frames, and drones near the top of the frame report higher altitudes than drones near the horizon.
- Pause the video. The radar stops updating too — the same blips stay on the screen. Seek backward; the radar rewinds with the video.

**Secure-coding check:**

- Configure CORS explicitly on the backend. Only allow your dev origin (for example, `http://localhost:5173`). Do not use `allow_origins=["*"]`.
- Validate the altitude config file. Latitude in `[-90, 90]`, longitude in `[-180, 180]`, FOV in `[10, 170]` degrees, elevation in `[0, 9000]` meters. Refuse to start the pipeline on bad data instead of silently defaulting.

**Done when:**

- [ ] Video plays in the UI, served by your backend.
- [ ] Bounding boxes overlay the video and roughly track moving drones.
- [ ] You can run with `DETECTOR=blob` or `DETECTOR=yolo` and see different results.
- [ ] A short detector comparison writeup is committed to your repo.
- [ ] Vector arrows on the radar point in directions that match on-screen motion.
- [ ] The inspector shows `altitude_m` with plausible, stable values.
- [ ] The radar follows the video: pausing the video pauses the radar, seeking the video moves the radar to that time.

---

## Week 23 — Replay and notes that persist

**What you're building.** Memory. Until now, everything is live and forgotten as soon as it scrolls past. You'll save tracks to a **SQLite** database (a single-file database that lives next to your code — no separate server to manage), add a way to play back any past time range on the radar, and persist commander notes in the browser's `localStorage` so they survive a refresh.

**Demo.** Scrub a timeline back in time and watch past drone activity replay on the radar. Commander notes you typed earlier are still there after refresh.

**Milestones:**

1. Create the database at `backend/data/radar.db`. Add a `track_samples` table with columns for `ts_ms, track_id, bearing, range_u, heading, rel_speed_u, altitude_m, confidence`, with an index on `ts_ms`. Enable WAL mode so the writer and a reader can coexist.
2. Write a `TrackSampleWriter` that buffers samples in memory and flushes to SQLite every 200 ms or every 500 rows, whichever comes first. Wire it into your pipeline at roughly 10 Hz.
3. Add `GET /replay?start_ms=...&end_ms=...&limit=...` to the backend. Return samples in the requested range as JSON. Validate the inputs: `start < end`, range no larger than 10 minutes, `limit ≤ 20000`.
4. Add `WS /ws/replay?start_ms=...&end_ms=...&rate=1&hz=10` that plays back stored samples at a configurable rate and message frequency, using the same JSON message format as `/ws/tracks`.
5. On the frontend, save commander notes per track to `localStorage`, keyed by track ID. Load on mount, write on change (debounce 500 ms). Add a control that switches the radar's data source between live (`/ws/tracks`) and replay (`/ws/replay`).

**Prompting:**

- *"Help me write `backend/app/db.py` that opens a SQLite database with WAL mode and creates a `track_samples` table with these columns. Return the connection."*
- *"Write `TrackSampleWriter` with `add_sample(dict)` and an internal flush every 200 ms or 500 rows. One transaction per flush. Cap the buffer at 5000 rows."*
- *"Add `GET /replay` to my FastAPI app. Accept `start_ms`, `end_ms`, `limit` as query params. Validate them. Use parameterized queries to fetch rows. Return JSON."*
- *"Add a `useLocalStorage(key, initialValue)` hook in React, then use it for commander notes keyed by track ID."*

**Verify:**

- After 30 seconds of live streaming, `sqlite3 backend/data/radar.db "select count(*) from track_samples"` returns roughly `store_hz × seconds × avg_tracks`.
- `curl 'http://127.0.0.1:8000/replay?start_ms=...&end_ms=...&limit=100'` returns valid JSON. An invalid range returns a 400.
- Type a note on a track, reload the page, the note is still there for the same track ID.

**Secure-coding check.** This is the SQL injection week. Every query parameter must go through parameterized SQL (`cursor.execute("... WHERE ts_ms >= ?", (start_ms,))`). Never f-string a parameter into a query.

**Done when:**

- [ ] The database file exists and grows during a live session.
- [ ] `/replay` returns valid JSON for valid inputs and 400 for invalid inputs.
- [ ] Notes survive a page refresh.
- [ ] You can switch the radar to a recent time range and watch the replay.

---

## Week 24 — Zones, events, and the AAR

**What you're building.** Mission awareness. The user can draw a region on the radar (a "zone"); the system watches drones enter, leave, and dwell inside it; every meaningful moment is captured in a downloadable After-Action Report.

**Demo.** Define a zone on the radar by clicking and dragging. When a drone crosses into the zone, an "enter" event appears in the event log. When it leaves, an "exit" event appears. If it lingers for five seconds, a "dwell" event fires. The "Export AAR" button downloads a real report.

**Milestones:**

1. Add `zones` and `events` tables to SQLite. Add CRUD endpoints: `GET /zones`, `POST /zones`, `DELETE /zones/{id}`. Zone geometry is normalized to `[0, 1]` (rectangle or polygon) so it does not depend on frame size.
2. Add a way to define zones. The shortest path is: define zones via `curl -X POST http://127.0.0.1:8005/zones -H 'Content-Type: application/json' -d '...'` from the terminal and load them into your engine on startup. If you have time, add a "draw zone" mode to the radar UI (click-drag a rectangle, prompt for a name, POST it). Zones must be stored in **normalized frame coordinates** (`x_u`, `y_u` in `[0, 1]`) so they are independent of frame size; the engine converts each track's bbox center to those coordinates for containment tests.
3. Write a zone event engine. For each `(track_id, zone_id)` pair, hold state: `outside | inside`, `enter_ts`, `dwell_emitted`. On every track update, evaluate containment and emit `enter`, `exit`, or `dwell` events on transitions. `dwell` fires once per stay after 5 continuous seconds.
4. Persist events to the `events` table. Stream them on the same `/ws/tracks` socket inside an `{"type": "events", "events": [...]}` message. The event log in the UI populates live.
5. Wire the "Export AAR" button. On click, fetch `/replay` and `/events` for the time range since the session started and produce a downloadable JSON file via `URL.createObjectURL` + an anchor click. Filename: `aar-<iso-timestamp>.json`. A simple PDF (`jsPDF` in the browser, or `reportlab` on the backend) is a stretch — JSON is fine for credit.

**Prompting:**

- *"Write a point-in-polygon test using ray-casting in Python. Points are normalized `(x, y)` in `[0, 1]`. Also a point-in-rect test. Return bool."*
- *"Given a stream of track updates and a list of zones, write a `ZoneEventEngine` that emits enter, exit, and dwell events. Maintain per-(track_id, zone_id) state. Dwell fires once after 5 continuous seconds inside."*
- *"My radar is an SVG. Add a 'draw zone' mode where the user clicks and drags to define a rectangle in radar coordinates. On mouseup, prompt for a name and POST to `/zones` with normalized coords."*
- *"Build a client-side AAR export. Fetch `/replay` and `/events` for the last 5 minutes, format as JSON, trigger a browser download named `aar-<timestamp>.json`."*

**Verify:**

- Draw a zone. A drone crossing it produces an enter event followed by an exit event in the log.
- A drone hovering inside a zone for at least 5 seconds produces exactly one dwell event for that stay.
- Click "Export AAR". A file downloads. Open it. It contains the recent tracks and events.

**Secure-coding check.** Validate zone geometry on the backend. Polygons with more than (say) 256 vertices, or coordinates outside `[0, 1]`, get rejected with a 400. Names are capped at 128 characters and stripped of control characters before insert.

**Done when:**

- [ ] A POST to `/zones` (or your UI's draw mode if you built it) persists a zone across restarts.
- [ ] Enter, exit, and dwell events fire correctly in the event log.
- [ ] "Export AAR" downloads a JSON file containing the session's tracks and events.

---

## Troubleshooting

- **"Address already in use" on port 8000.** Pick another port (`--port 8001`) or find what is using it: `lsof -i :8000` on macOS/Linux, `netstat -ano | findstr :8000` on Windows.
- **OpenCV install fails on Apple Silicon.** Use `pip install opencv-python-headless` instead of `opencv-python`. The headless build does not need the macOS GUI dependencies.
- **WebSocket fails to connect from the browser.** Check the URL (`ws://`, not `wss://`), the port, and CORS settings. The browser dev tools Console and Network tabs will tell you which.
- **Video will not play in the browser.** Your MP4 codec may not be web-compatible. Re-encode: `ffmpeg -i in.mp4 -c:v libx264 -pix_fmt yuv420p -movflags +faststart out.mp4`.
- **SQLite "database is locked".** You probably do not have WAL mode enabled, or you have multiple writer processes. One writer is enough.
- **"Module not found" right after `pip install`.** Wrong virtual environment is active. Run `which python` and `which pip`; both should point inside `backend/.venv/bin`.
- **`ultralytics` install is slow or fails.** It pulls in PyTorch, which is a big download. On a flaky network, run `pip install ultralytics --no-cache-dir` and let it complete uninterrupted. On Apple Silicon, install with `pip install ultralytics torch` and let pip resolve a compatible version.
- **uvicorn keeps reloading after `pip install`.** The `--reload` flag watches every file under the directory it is launched in. When pip drops new files into `.venv/`, uvicorn sees them as code changes. Use `--reload-dir app` so it watches only your source directory.
- **`pip install ultralytics` hangs.** Torch is several hundred MB. Run the install in a separate terminal so you can keep coding; ultralytics imports lazily, so the rest of your backend works without it until you import `YoloDetector`.

When you cannot solve a problem after 20 minutes, ask your AI assistant — but copy the error message exactly and include the file and line it points to. Vague descriptions get vague answers.

---

## Secure-coding final pass

By the end of the project, your system has several externally reachable surfaces: the HTTP API, the WebSocket, the file upload (if you add one), and the SQLite database. Before you demo, walk through this checklist:

- Every HTTP and WebSocket parameter from the client is validated. Out-of-range values return 400, not a stack trace.
- All SQL uses parameterized queries. There are no f-strings or string concatenations building queries.
- No secrets in the repository. `.env` is in `.gitignore`. API keys, if you have any, live in environment variables.
- CORS is an allowlist, not `*`.
- Dependencies are pinned (`requirements.txt`, `package.json`). Run `pip list --outdated` and `npm audit` and fix what is critical.
- A short threat model lives in the repository (one page is fine): who could attack the system, what they would want, and the simplest mitigation you put in place.

---

## Stretch goals

If you finish early, pick one or two:

- Add JWT-based authentication and per-IP rate limiting to the API.
- Containerize the backend and frontend with Docker.
- Deploy the system to a small cloud VM or to Fly.io.
- Add a second camera, register the two views, and fuse the detections.
- Generate a richer AAR PDF that includes a timeline chart of events and a small map showing zones.
