#!/bin/bash
# =============================================================================
# Beer Pro — Chromium Kiosk Launcher
# =============================================================================
# Launches Chromium in full-screen kiosk mode pointing at the local Beer Pro
# server. Intended to run as a systemd service on the Pi so the HDMI display
# shows the scoreboard on boot without a desktop environment.
#
# Requires: chromium (Debian bookworm), xserver-xorg, x11-xserver-utils, unclutter
#   sudo apt-get install -y chromium xserver-xorg xinit x11-xserver-utils unclutter
# =============================================================================

# Wait for the Beer Pro server to be ready
echo "Waiting for Beer Pro server..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8080/ >/dev/null 2>&1; then
        echo "Server ready."
        break
    fi
    sleep 1
done

# Disable screen blanking and power management
xset s off
xset s noblank
xset -dpms

# Hide the mouse cursor after 1 second of inactivity
unclutter -idle 1 -root &

# Launch Chromium in kiosk mode
# Binary is 'chromium' on Debian bookworm (not 'chromium-browser')
CHROMIUM=$(command -v chromium || command -v chromium-browser)
"$CHROMIUM" \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-restore-session-state \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --check-for-update-interval=31536000 \
    --no-first-run \
    --fast \
    --fast-start \
    --disable-features=TranslateUI \
    http://localhost:8080/
