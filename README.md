# 🍺 Beer Pro

```
  ____                 ____
 |  _ \               |  _ \ _ __ ___
 | |_) | ___  ___ _ __| |_) | '__/ _ \
 |  _ < / _ \/ _ \ '__|  __/| | | (_) |
 |_| \_\\___/\___/_|  |_|   |_|  \___/
```

**The scoreboard your beer pong table deserves.**

A Raspberry Pi-powered live scoreboard and 4× slow-motion instant replay system.
A USB numpad keeps score. The camera never misses a shot. Every browser in the room
stays in sync. And when someone finally makes that miracle cup, you can watch it again
— in glorious slow motion — on the TV.

[![Version](https://img.shields.io/badge/version-1.1.0-f5c518?style=flat-square)](https://github.com/mattdmitch/beerpro/releases)
[![Python](https://img.shields.io/badge/python-3.9%2B-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Pi](https://img.shields.io/badge/Raspberry%20Pi-3B%2B%20%2F%204-c51a4a?style=flat-square&logo=raspberrypi&logoColor=white)](https://raspberrypi.com)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

---

## What it does

| Feature | Details |
|---|---|
| **Live scoreboard** | Big, TV-optimised display with score trail dots and match win counter |
| **Instant slow-mo replay** | Captures 120fps from a USB camera, stores a rolling 4-second buffer, streams it back at 30fps (4× slow-motion) as MJPEG |
| **Real-time sync** | WebSocket pushes every change to every connected phone, tablet, and TV simultaneously |
| **Score animations** | Digit bump, panel flash, and particle burst fire on every point. Confetti cannon on game win. |
| **Mobile controls** | Touch-friendly +/− buttons auto-appear on phones — no numpad required for spectators to control the game |
| **Match tracking** | Win counts persist across games within a session |
| **Settings page** | Rename teams, reset match history, change WiFi, update firmware — all from the browser |
| **OTA updates** | Paste a URL → check → apply. Downloads, verifies SHA256, backs up, installs, restarts. One tap rollback too. |
| **WiFi setup mode** | First boot shows a step-by-step TV splash with QR code. Your phone connects and walks you through joining your home WiFi. |
| **Dev mode** | Runs on macOS/Windows for testing — keyboard fallback, no camera required |

---

## Hardware

You need exactly four things. You probably already have two of them.

| Part | Notes |
|---|---|
| **Raspberry Pi 4** (or 3B+) | Any Pi with USB ports and built-in WiFi. Pi 4 recommended for 120fps camera processing. |
| **USB camera (120fps capable)** | Logitech C922, C920, or any V4L2 camera that does MJPEG at 120fps. Check the specs — most "gaming" webcams qualify. |
| **USB numpad** | Any standard USB number pad. You can plug in two and both work simultaneously. |
| **HDMI TV or monitor** | For the scoreboard display. Any size, any TV. The layout scales. |

> **Tip:** The Pi is configured as a WiFi access point (`BeerPro`, IP `192.168.4.1`) so
> players can connect their phones directly — no router needed at the ping pong table.
> After first-boot setup you can join it to your home WiFi instead.

---

## Setup

### Raspberry Pi — Full Production Setup

This covers everything from a fresh SD card to a running scoreboard.

#### 1. Flash Pi OS

Download and flash **Raspberry Pi OS Lite (64-bit)** using
[Raspberry Pi Imager](https://raspberrypi.com/software/).

In Imager's advanced settings before flashing:
- Set a hostname: `beerpro`
- Enable SSH, set a username/password
- (Optional) pre-configure your home WiFi so you can SSH in on first boot

#### 2. Boot and SSH in

```bash
ssh pi@beerpro.local
```

#### 3. Install system dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git \
    hostapd dnsmasq libcap2-bin
```

#### 4. Clone the repo

```bash
cd ~
git clone https://github.com/mattdmitch/beerpro.git
cd beerpro
```

#### 5. Create virtualenv and install Python deps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install evdev          # Linux-only USB keypad driver
```

#### 6. Configure the WiFi access point

This turns the Pi into a hotspot so phones can connect directly.

**`/etc/hostapd/hostapd.conf`** — create or overwrite:
```ini
interface=wlan0
driver=nl80211
ssid=BeerPro
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
```

**`/etc/dnsmasq.conf`** — append:
```ini
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
```

**`/etc/dhcpcd.conf`** — append:
```ini
interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
```

Enable and start:
```bash
sudo systemctl unmask hostapd
sudo systemctl enable hostapd dnsmasq
sudo systemctl start hostapd dnsmasq
```

> **Note:** Once the AP is active your Pi will no longer auto-connect to your
> home WiFi on boot. Use the Beer Pro settings page (after step 8) to join your
> home network if you want internet access on the Pi.

#### 7. Create the systemd service

```bash
sudo tee /etc/systemd/system/beerpro.service > /dev/null << 'EOF'
[Unit]
Description=Beer Pro Scoreboard
After=network.target

[Service]
Type=notify
User=pi
WorkingDirectory=/home/pi/beerpro
ExecStart=/home/pi/beerpro/.venv/bin/python main.py
Restart=on-failure
RestartSec=5
WatchdogSec=60

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable beerpro
sudo systemctl start beerpro
```

#### 8. Check it's running

```bash
sudo systemctl status beerpro
# or tail the logs live:
sudo journalctl -u beerpro -f
```

Point a browser (or the HDMI TV's browser) at `http://192.168.4.1:8080` — you should
see the scoreboard.

#### 9. First-boot WiFi setup (optional)

If you want the Pi on your home network (for OTA updates, internet access, etc.):

1. The TV shows a **First-Time Setup** splash with a QR code
2. Scan it with your phone (or connect to the `BeerPro` WiFi and go to `192.168.4.1:8080`)
3. Your phone shows a network scan — pick your home WiFi, enter the password
4. Beer Pro connects and the TV transitions to the scoreboard

To reset WiFi later: **Settings → Change WiFi Network**.

---

### macOS / Windows — Dev Mode

No Pi, no camera, no problem. Good for working on the UI or game logic.

```bash
# Clone
git clone https://github.com/mattdmitch/beerpro.git
cd beerpro

# Install deps (skip evdev — Linux only)
pip install fastapi "uvicorn[standard]" opencv-python-headless

# Optional: keyboard input without pressing Enter each time
pip install pynput

# Run
python main.py
```

Open `http://localhost:8080` in a browser.

Press **1–5** in the terminal to control the game (or **1–5 + Enter** if pynput isn't installed).

---

## Key Bindings

| Key | Action |
|-----|--------|
| `1` | Team 1 +1 point |
| `2` | Team 1 −1 point |
| `3` | Team 2 +1 point |
| `4` | Team 2 −1 point |
| `5` | Trigger slow-mo replay |
| Any key *(during replay)* | Stop replay, return to scoreboard |
| Any key *(after game over)* | Reset for a new game |

---

## OTA Updates

Beer Pro can update itself from a URL. No SSH required.

#### Releasing a new version

1. Make your changes and bump `VERSION` (e.g. `1.2.0`)
2. Build the zip (must contain only whitelisted files — see below):
   ```bash
   zip -r beerpro-v1.2.0.zip \
     main.py server.py camera.py config.py game_state.py \
     input_handler.py wifi_manager.py update_manager.py \
     requirements.txt VERSION static/
   ```
3. Create a `manifest.json`:
   ```json
   {
     "version": "1.2.0",
     "sha256": "<sha256 of the zip>",
     "changelog": "What changed in this release"
   }
   ```
4. Host both files somewhere publicly accessible (GitHub Releases works perfectly)
5. In Beer Pro settings, paste the zip URL → **Check** → **Apply Update**

The updater will:
1. Fetch the manifest, verify the version
2. Download and SHA256-verify the zip
3. Validate zip contents against the whitelist (no system files can be touched)
4. Backup the current app
5. Extract new files
6. Reinstall pip deps if `requirements.txt` changed
7. Restart the `beerpro` systemd service

If anything goes wrong, hit **Rollback** to restore the previous version.

#### Allowed files in update zips

```
main.py  server.py  camera.py  config.py  game_state.py
input_handler.py  wifi_manager.py  update_manager.py
requirements.txt  VERSION  static/
```

System config files (`hostapd`, `dnsmasq`, etc.) are never touched.

---

## Configuration

All tunable constants live in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `TARGET_SCORE` | `11` | First to this score wins |
| `WIN_BY` | `2` | Must win by this margin (no cap) |
| `CAMERA_INDEX` | `0` | USB camera device index (try 1, 2 if not found) |
| `CAMERA_FPS` | `120` | Target capture framerate |
| `CAMERA_WIDTH` | `1280` | Capture resolution width |
| `CAMERA_HEIGHT` | `720` | Capture resolution height |
| `BUFFER_SECONDS` | `4` | Rolling replay buffer length |
| `REPLAY_CLIP_SECONDS` | `2.0` | How far back the replay starts |
| `REPLAY_PLAYBACK_FPS` | `30` | Replay stream framerate (30fps from 120fps = 4× slow-mo) |
| `JPEG_QUALITY` | `70` | JPEG quality for buffered frames (0–100) |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8080` | Server port |

---

## Architecture

```
main.py
  ├── camera.py          — Background thread: 120fps USB capture → rolling JPEG deque
  ├── input_handler.py   — evdev (Linux) or stdin/pynput (dev) → dispatches to game_state
  ├── game_state.py      — Scoring logic, win detection, replay state, WebSocket broadcast
  ├── wifi_manager.py    — wpa_cli wrapper: scan, connect, forget, status
  ├── update_manager.py  — OTA: download, verify, backup, extract, restart
  └── server.py          — FastAPI: HTTP routes, WebSocket hub, MJPEG replay stream
        └── static/
              ├── index.html   — Single-page app (6 views: scoreboard, replay, game-over, settings, setup, tv-setup)
              ├── app.js       — WebSocket client, view router, score/dot/confetti rendering, mobile controls
              └── style.css    — Full-screen TV layout + mobile responsive
```

### Data flow — scoring

```
USB numpad keypress
  → input_handler (evdev thread)
    → asyncio.run_coroutine_threadsafe → game_state.handle_key()
      → score_up() / score_down()
        → WebSocket broadcast to all clients
          → browser updates score + trail dots + animations
```

### Data flow — replay

```
Key 5 pressed
  → game_state.start_replay()
    → WebSocket broadcast: { type: "replay_start" }
      → browser sets <img src="/replay/stream?t=...">
        → server snapshots camera deque (last 2s of JPEG frames)
          → streams as MJPEG multipart at 30fps (4× slow-motion) in worker thread
Key pressed again
  → game_state.stop_replay()
    → WebSocket broadcast: { type: "replay_stop" }
      → browser clears <img src>, returns to scoreboard
```

---

## API Reference

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves the SPA |
| `GET` | `/api/state` | Current game state snapshot (JSON) |
| `POST` | `/api/settings` | Update team names. Body: `{ "team1": "...", "team2": "..." }` |
| `POST` | `/api/reset_match` | Reset all scores, wins, and match history |
| `POST` | `/api/score` | Adjust score. Body: `{ "team": 1\|2, "delta": 1\|-1 }` |
| `POST` | `/api/replay` | Toggle replay on/off |
| `GET` | `/api/history` | Completed game records array |
| `GET` | `/api/camera` | Camera status: `{ ok, buffer_frames, buffer_seconds }` |
| `GET` | `/api/wifi/status` | Current WiFi status |
| `GET` | `/api/wifi/scan` | Scan for nearby networks |
| `POST` | `/api/wifi/connect` | Connect to a network. Body: `{ "ssid": "...", "password": "..." }` |
| `POST` | `/api/wifi/forget` | Clear saved credentials, re-enter setup mode |
| `GET` | `/api/update/version` | Installed version string |
| `POST` | `/api/update/check` | Check manifest at URL. Body: `{ "url": "..." }` |
| `POST` | `/api/update/apply` | Download and apply update. Body: `{ "url": "..." }` |
| `POST` | `/api/update/rollback` | Restore previous backup |
| `GET` | `/replay/stream` | MJPEG multipart replay stream |
| `GET` | `/replay/latest` | Single most-recent camera frame as JPEG |

### WebSocket — `/ws`

#### Server → Client

| `type` | Key fields | Description |
|---|---|---|
| `score` | `t1`, `t2`, `team1`, `team2`, `match`, `history` | Score updated |
| `settings` | `team1`, `team2`, `match` | Team names / match wins changed |
| `game_over` | `winner`, `score`, `match`, `team1`, `team2` | Win condition reached |
| `reset` | `team1`, `team2`, `match` | New game started |
| `replay_start` | — | Replay mode activated |
| `replay_stop` | — | Replay mode ended |
| `setup_mode` | — | Device is in first-boot WiFi setup |
| `setup_complete` | `ip`, `ssid` | WiFi connected successfully |
| `update_progress` | `stage`, `pct` | OTA update progress |
| `update_complete` | `version` | OTA update finished, restarting |
| `update_failed` | `error` | OTA update failed |
| `ping` | — | Keepalive every 30 s |

#### Client → Server

| `type` | Fields | Description |
|---|---|---|
| `key` | `key` (`KEY_1`–`KEY_5`) | Remote keypress (mobile controls) |
| `settings` | `team1`, `team2` | Update team names |
| `reset_match` | — | Full match reset |

---

## Releasing a new version (maintainer notes)

```bash
# 1. Make changes, bump VERSION file
echo "1.2.0" > VERSION

# 2. Commit
git add .
git commit -m "Release v1.2.0 — description of changes"

# 3. Tag
git tag v1.2.0

# 4. Push branch + tags
git push && git push --tags

# 5. Build the update zip
zip -r beerpro-v1.2.0.zip \
  main.py server.py camera.py config.py game_state.py \
  input_handler.py wifi_manager.py update_manager.py \
  requirements.txt VERSION static/

# 6. Generate SHA256
shasum -a 256 beerpro-v1.2.0.zip

# 7. Create manifest
cat > beerpro-v1.2.0.zip.manifest << EOF
{
  "version": "1.2.0",
  "sha256": "<paste sha256 here>",
  "changelog": "Short description of what changed"
}
EOF

# 8. Create GitHub release with both files as assets
gh release create v1.2.0 \
  --title "v1.2.0 — Description" \
  --notes-file CHANGELOG.md \
  beerpro-v1.2.0.zip \
  beerpro-v1.2.0.zip.manifest
```

The release zip URL can then be pasted directly into the Beer Pro **Settings → Update URL** field.

---

## Contributing

Bug reports, feature ideas, and PRs are welcome. Open an issue first for anything major.

The project has no build step — it's plain Python + vanilla JS. `python main.py` and you're running.

---

*Built for the table. Optimised for chaos.*
