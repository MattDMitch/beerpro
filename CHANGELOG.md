# Changelog

All notable changes to Beer Pro are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versions follow [Semantic Versioning](https://semver.org/).

---

## [1.1.0] — 2026-03-22

### Added
- **Score animations** — score digits scale-bump on every point; full panel flash for each team
- **Particle burst** — 8-point particle explosion fires from the score digit on each point scored
- **Confetti** — 60-piece confetti cannon fires on game win screen
- **Mobile controls** — touch-friendly +/− score buttons and replay button appear automatically on phones/tablets; sends via WebSocket with REST fallback
- **OTA software updates** — Settings page now has a URL-based update system: check manifest, verify SHA256, backup current app, extract new files, reinstall deps, restart service via `systemctl`
- **Rollback** — one-click rollback to the previous backup from the Settings page
- **WiFi setup mode** — first-boot splash on the TV with QR code + step-by-step instructions; phone gets a network scan + connect form
- **`wifi_manager.py`** — full `wpa_cli`-based WiFi scan, connect, forget, and status reporting
- **`update_manager.py`** — full OTA pipeline with whitelisted zip extraction and SHA256 verification
- **WebSocket key dispatch** — browsers can now send `{ type: "key", key: "KEY_1" }` messages to control the game remotely (used by mobile controls)
- **`/api/score` and `/api/replay`** REST endpoints for mobile control fallback
- **systemd-notify support** — `READY=1` signal sent to systemd watchdog on startup

### Changed
- Score trail dots now correctly shrink when a point is removed (reads from current score, not history length)
- `REPLAY_CLIP_SECONDS` config constant controls replay window independently of buffer size (default: 2.0 s of a 4 s buffer)
- MJPEG replay stream now runs in a per-client worker thread — slow/distant clients no longer stall the asyncio event loop
- WebSocket ping interval reduced to 30 s with `asyncio.wait_for` timeout to detect dead connections faster
- Camera capture loop uses `CAP_V4L2` backend on Linux first, falls back to default (macOS dev)

### Fixed
- Settings form pre-fills with current team names when opened
- Match record display updates correctly after a full match reset

---

## [1.0.0] — Initial release

- Live scoreboard web app served by FastAPI + uvicorn
- Real-time multi-client sync via WebSocket
- 120fps USB camera rolling buffer (4 s, ~14 MB)
- 4× slow-motion MJPEG instant replay streamed to browser
- USB numpad input via evdev (Linux) with stdin/pynput fallback (dev)
- Score trail dots, match win tracking, team name settings
- Cross-platform dev mode (macOS/Windows, no camera required)
