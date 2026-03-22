# server.py — FastAPI server: HTTP, WebSocket, MJPEG replay stream

import asyncio
import json
import logging
import time
import threading
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
from game_state import state
from camera import camera
import wifi_manager
import update_manager

logger = logging.getLogger(__name__)

app = FastAPI(title="Beer Pro")

# Mount static files (index.html, style.css, app.js)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ------------------------------------------------------------------
# WebSocket connection manager
# ------------------------------------------------------------------

class ConnectionManager:
    def __init__(self) -> None:
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)
        logger.info(f"WS client connected. Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)
        logger.info(f"WS client disconnected. Total: {len(self.active)}")

    async def broadcast(self, msg: dict) -> None:
        if not self.active:
            return
        data = json.dumps(msg)
        dead = set()
        for ws in list(self.active):
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active.discard(ws)


manager = ConnectionManager()

# Register broadcast function with game state
async def _broadcast(msg: dict) -> None:
    await manager.broadcast(msg)

state.set_broadcast(_broadcast)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

def _spa() -> HTMLResponse:
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/", response_class=HTMLResponse)
async def index():
    return _spa()


@app.get("/setup", response_class=HTMLResponse)
async def setup_page():
    """WiFi setup page — same SPA, client-side routing handles the view."""
    return _spa()


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    """Settings page is the same SPA — routing handled client-side."""
    return _spa()


# ------------------------------------------------------------------
# WebSocket endpoint
# ------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    # Send current state snapshot immediately on connect
    try:
        await ws.send_text(json.dumps(state.snapshot()))
        # Also send settings so client knows team names + match wins
        await ws.send_text(json.dumps(state._settings_msg()))
    except Exception:
        pass

    try:
        # Keep connection alive; client messages not expected but handled
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                # Client can send settings updates via WS as well
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "settings":
                        await state.update_settings(
                            msg.get("team1", ""),
                            msg.get("team2", ""),
                        )
                    elif msg.get("type") == "reset_match":
                        await state.reset_match()
                    elif msg.get("type") == "key":
                        key = msg.get("key", "")
                        if key in ("KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5"):
                            await state.handle_key(key)
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    await ws.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)


# ------------------------------------------------------------------
# REST API for settings (used by the settings page form)
# ------------------------------------------------------------------

@app.post("/api/settings")
async def api_settings(request: Request):
    body = await request.json()
    team1 = body.get("team1", "").strip()
    team2 = body.get("team2", "").strip()
    await state.update_settings(team1, team2)
    return JSONResponse({"ok": True, "team1": state.team1_name, "team2": state.team2_name})


@app.post("/api/reset_match")
async def api_reset_match():
    await state.reset_match()
    return JSONResponse({"ok": True})


@app.post("/api/score")
async def api_score(request: Request):
    """Mobile control: adjust score. Body: { team: 1|2, delta: 1|-1 }"""
    body = await request.json()
    team  = int(body.get("team", 0))
    delta = int(body.get("delta", 0))
    if team not in (1, 2):
        return JSONResponse({"ok": False, "error": "team must be 1 or 2"}, status_code=400)
    if delta == 1:
        await state.score_up(team)
    elif delta == -1:
        await state.score_down(team)
    else:
        return JSONResponse({"ok": False, "error": "delta must be 1 or -1"}, status_code=400)
    return JSONResponse({"ok": True, "t1": state.score_t1, "t2": state.score_t2})


@app.post("/api/replay")
async def api_replay():
    """Mobile control: toggle replay on/off."""
    if state.replay_active:
        await state.stop_replay()
    else:
        await state.start_replay()
    return JSONResponse({"ok": True, "replay_active": state.replay_active})


@app.get("/api/state")
async def api_state():
    return JSONResponse(state.snapshot())


# ------------------------------------------------------------------
# WiFi setup API
# ------------------------------------------------------------------

@app.get("/api/wifi/status")
async def api_wifi_status():
    """Return current WiFi configuration and connection state."""
    status = wifi_manager.current_status()
    status["setup_mode"] = state.setup_mode
    return JSONResponse(status)


@app.get("/api/wifi/scan")
async def api_wifi_scan():
    """
    Scan for nearby WiFi networks.
    Returns sorted list: [ { ssid, signal (0-100), secured }, ... ]
    This runs wpa_cli scan in a thread so it doesn't block the event loop.
    """
    loop = asyncio.get_running_loop()
    networks = await loop.run_in_executor(None, wifi_manager.scan_networks)
    return JSONResponse({"networks": networks})


@app.post("/api/wifi/connect")
async def api_wifi_connect(request: Request):
    """
    Attempt to connect to a WiFi network.
    Body: { "ssid": "...", "password": "..." }
    Returns: { "ok": bool, "ip": str, "error": str }
    """
    body = await request.json()
    ssid = body.get("ssid", "").strip()
    password = body.get("password", "")

    if not ssid:
        return JSONResponse({"ok": False, "ip": "", "error": "SSID is required"}, status_code=400)

    # Run blocking connect() in a thread — it sleeps up to 15s waiting for DHCP
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, wifi_manager.connect, ssid, password)

    if result["ok"]:
        # Exit setup mode — broadcast to all clients so TV splash disappears
        state.set_setup_mode(False)
        await manager.broadcast({"type": "setup_complete", "ip": result["ip"], "ssid": ssid})

    return JSONResponse(result)


@app.post("/api/wifi/forget")
async def api_wifi_forget():
    """Clear saved WiFi credentials and re-enter setup mode."""
    wifi_manager.forget()
    state.set_setup_mode(True)
    await manager.broadcast({"type": "setup_mode"})
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------
# OTA Update API
# ------------------------------------------------------------------

@app.get("/api/update/version")
async def api_update_version():
    """Return the current installed version."""
    return JSONResponse({"version": update_manager.get_current_version()})


@app.post("/api/update/check")
async def api_update_check(request: Request):
    """
    Check if an update is available at the given URL.
    Body: { "url": "https://..." }
    Returns: { ok, current_version, new_version, changelog, is_newer, error }
    """
    body = await request.json()
    url = body.get("url", "").strip()
    if not url:
        return JSONResponse({"ok": False, "error": "URL is required"}, status_code=400)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, update_manager.check_update, url)
    return JSONResponse(result)


@app.post("/api/update/apply")
async def api_update_apply(request: Request):
    """
    Download and apply an update from the given URL.
    Body: { "url": "https://..." }
    Progress is broadcast over WebSocket as { type: "update_progress", stage, pct }.
    On completion broadcasts { type: "update_complete", version } or { type: "update_failed", error }.
    Returns immediately with { ok: true, message: "Update started" }.
    """
    body = await request.json()
    url = body.get("url", "").strip()
    if not url:
        return JSONResponse({"ok": False, "error": "URL is required"}, status_code=400)

    async def _run_update():
        # Capture the running loop BEFORE entering the thread executor so the
        # _progress callback (which runs in a worker thread) can schedule
        # coroutines back onto it without calling get_event_loop().
        loop = asyncio.get_running_loop()

        def _progress(stage, pct):
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "update_progress", "stage": stage, "pct": pct}),
                loop,
            )

        result = await loop.run_in_executor(
            None, update_manager.apply_update, url, _progress
        )

        if result["ok"]:
            await manager.broadcast({
                "type": "update_complete",
                "version": result["version"],
            })
        else:
            await manager.broadcast({
                "type": "update_failed",
                "error": result["error"],
            })

    asyncio.ensure_future(_run_update())
    return JSONResponse({"ok": True, "message": "Update started"})


@app.post("/api/update/rollback")
async def api_update_rollback():
    """Roll back to the previous version backup."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, update_manager.rollback)
    if result["ok"]:
        await manager.broadcast({"type": "update_complete", "version": "rollback"})
    return JSONResponse(result)


@app.get("/api/history")
async def api_history():
    history = [
        {
            "winner": r.winner,
            "score": [r.score_t1, r.score_t2],
            "duration": round(r.duration_seconds),
            "points": r.point_history,
        }
        for r in state.match_history
    ]
    return JSONResponse({"history": history})


# ------------------------------------------------------------------
# MJPEG replay stream
# ------------------------------------------------------------------

def _mjpeg_iter_sync(frames: list, stop_event: threading.Event):
    """
    Synchronous generator that yields MJPEG multipart chunks.
    Runs entirely in a worker thread — blocking time.sleep() is safe here
    and does NOT stall the asyncio event loop or other HTTP/WS connections.

    Loops through the snapshot until the stop_event is set (replay ended)
    or the client disconnects (GeneratorExit / send failure).
    """
    frame_delay = 1.0 / config.REPLAY_PLAYBACK_FPS
    total = len(frames)
    idx = 0

    while not stop_event.is_set():
        frame_data = frames[idx % total]
        idx += 1

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + frame_data
            + b"\r\n"
        )

        time.sleep(frame_delay)


@app.get("/replay/stream")
async def replay_stream():
    """
    MJPEG stream endpoint. Browsers point an <img> tag here during replay.

    Each client gets its own snapshot of the camera buffer and its own worker
    thread for frame pacing. This prevents slow/distant clients (e.g. phones
    over WiFi) from stalling the event loop and delaying other connections.
    """
    # Snapshot the rolling buffer and trim to the configured clip window
    clip_frames = int(config.REPLAY_CLIP_SECONDS * config.CAMERA_FPS)
    frames = camera.snapshot()[-clip_frames:]

    if not frames:
        return JSONResponse(
            {"error": "No camera footage available"},
            status_code=503,
        )

    # stop_event is set when game_state marks replay as inactive,
    # which terminates the per-client thread cleanly.
    stop_event = threading.Event()

    async def _watch_replay_stop():
        """Async task: polls game state and sets stop_event when replay ends."""
        while state.replay_active:
            await asyncio.sleep(0.1)
        stop_event.set()

    asyncio.ensure_future(_watch_replay_stop())

    def _frame_generator():
        yield from _mjpeg_iter_sync(frames, stop_event)

    return StreamingResponse(
        _frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )


@app.get("/replay/latest")
async def replay_latest():
    """Return the single most recent camera frame as a JPEG (for thumbnail/debug)."""
    frame = camera.latest_frame_jpeg()
    if not frame:
        return JSONResponse({"error": "No frame available"}, status_code=503)
    return StreamingResponse(
        iter([frame]),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


# ------------------------------------------------------------------
# Camera status
# ------------------------------------------------------------------

@app.get("/api/camera")
async def camera_status():
    return JSONResponse({
        "ok": camera.camera_ok,
        "buffer_frames": len(camera.snapshot()),
        "buffer_seconds": round(len(camera.snapshot()) / max(config.CAMERA_FPS, 1), 1),
    })
