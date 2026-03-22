# config.py — Beer Pro configuration constants

# Game rules
TARGET_SCORE = 11       # First to this score wins
WIN_BY = 2              # Must win by this margin (no cap)

# Camera
CAMERA_INDEX = 0        # USB camera device index (try 0, 1, 2 if not found)
CAMERA_FPS = 120        # Target capture framerate
CAMERA_WIDTH = 1280     # Capture width (720p to keep buffer manageable)
CAMERA_HEIGHT = 720     # Capture height

# Rolling replay buffer
BUFFER_SECONDS = 4      # Seconds of footage to keep in rolling buffer
BUFFER_MAXFRAMES = CAMERA_FPS * BUFFER_SECONDS  # 720 frames

# Replay playback
REPLAY_PLAYBACK_FPS = 30   # Serve frames at this rate (4x slow-mo from 120fps source)
REPLAY_CLIP_SECONDS = 2.0  # How far back replay starts (independent of buffer size)
JPEG_QUALITY = 70          # JPEG compression quality for buffered frames (0-100)

# Networking
HOST = "0.0.0.0"
PORT = 8080

# Key mappings (standard number key codes via evdev)
KEY_T1_UP   = "KEY_1"
KEY_T1_DOWN = "KEY_2"
KEY_T2_UP   = "KEY_3"
KEY_T2_DOWN = "KEY_4"
KEY_REPLAY  = "KEY_5"

# Default team names (reset on each boot)
DEFAULT_TEAM1_NAME = "Team 1"
DEFAULT_TEAM2_NAME = "Team 2"

# WiFi info shown in web UI footer
WIFI_SSID = "BeerPro"
WIFI_IP   = "192.168.4.1"
