#!/bin/bash -e
# stageB/03-app/01-run.sh
# Install Python venv, deps, and bundle qrcode.min.js inside the chroot
on_chroot << EOF

APP_DIR="/home/pi/beerpro"

# ---- Create Python virtualenv -----------------------------------------------
echo "[stageB/03-app] Creating Python venv..."
sudo -u pi python3 -m venv "\${APP_DIR}/.venv"

# ---- Install Python dependencies --------------------------------------------
echo "[stageB/03-app] Installing Python dependencies..."
sudo -u pi "\${APP_DIR}/.venv/bin/pip" install --upgrade pip --quiet
sudo -u pi "\${APP_DIR}/.venv/bin/pip" install \
    -r "\${APP_DIR}/requirements.txt" \
    --quiet

# Install evdev (USB keypad input) and python-systemd for watchdog
sudo -u pi "\${APP_DIR}/.venv/bin/pip" install evdev --quiet 2>/dev/null || true
sudo -u pi "\${APP_DIR}/.venv/bin/pip" install systemd-python --quiet 2>/dev/null || true

# ---- Download and bundle qrcode.min.js (replace CDN reference) -------------
echo "[stageB/03-app] Bundling qrcode.min.js..."
QRCODE_URL="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"
QRCODE_DEST="\${APP_DIR}/static/qrcode.min.js"

if curl -fsSL --max-time 30 "\${QRCODE_URL}" -o "\${QRCODE_DEST}" 2>/dev/null; then
    chown pi:pi "\${QRCODE_DEST}"
    sed -i \
        's|https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/[^"]*"|/static/qrcode.min.js"|g' \
        "\${APP_DIR}/static/index.html"
    sed -i \
        's| integrity="[^"]*"||g; s| crossorigin="[^"]*"||g; s| referrerpolicy="[^"]*"||g' \
        "\${APP_DIR}/static/index.html"
    echo "  Bundled qrcode.min.js and patched index.html"
else
    echo "  WARNING: Could not download qrcode.min.js (no internet during build?)"
fi

# ---- Create /data placeholder directory ------------------------------------
mkdir -p /data
chown pi:pi /data

EOF
