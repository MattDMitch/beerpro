#!/bin/bash -e
# stageB/04-kiosk/00-run.sh
# Copy kiosk config files into rootfs

mkdir -p "${ROOTFS_DIR}/etc/xdg/openbox"
install -m 644 files/etc/xdg/openbox/autostart \
    "${ROOTFS_DIR}/etc/xdg/openbox/autostart"
