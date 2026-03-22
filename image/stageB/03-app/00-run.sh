#!/bin/bash -e
# stageB/03-app/00-run.sh
# Copy Beer Pro app files into rootfs

APP_DEST="${ROOTFS_DIR}/home/pi/beerpro"
mkdir -p "${APP_DEST}/static" "${APP_DEST}/scripts"

# ---- Python app files -------------------------------------------------------
for f in main.py server.py camera.py config.py game_state.py \
          input_handler.py wifi_manager.py update_manager.py \
          requirements.txt VERSION; do
    if [ -f "files/home/pi/beerpro/${f}" ]; then
        install -m 644 "files/home/pi/beerpro/${f}" "${APP_DEST}/${f}"
    else
        echo "WARNING: ${f} not found in stageB/03-app/files/"
    fi
done

# ---- Static web assets ------------------------------------------------------
for f in index.html app.js style.css; do
    if [ -f "files/home/pi/beerpro/static/${f}" ]; then
        install -m 644 "files/home/pi/beerpro/static/${f}" "${APP_DEST}/static/${f}"
    fi
done

# ---- Scripts ----------------------------------------------------------------
for f in kiosk.sh beerpro.service kiosk.service setup_ap.sh; do
    if [ -f "files/home/pi/beerpro/scripts/${f}" ]; then
        install -m 755 "files/home/pi/beerpro/scripts/${f}" "${APP_DEST}/scripts/${f}"
    fi
done

# ---- Fix ownership ----------------------------------------------------------
chown -R 1000:1000 "${APP_DEST}"
