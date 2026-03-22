#!/bin/bash -e
# stageB/01-sys-tweaks/00-run.sh
# Copy config files into rootfs BEFORE the chroot commands in 01-run.sh

# ---- Systemd service units --------------------------------------------------
install -m 644 files/etc/systemd/system/uap0.service \
    "${ROOTFS_DIR}/etc/systemd/system/uap0.service"
install -m 644 files/etc/systemd/system/beerpro.service \
    "${ROOTFS_DIR}/etc/systemd/system/beerpro.service"
install -m 644 files/etc/systemd/system/kiosk.service \
    "${ROOTFS_DIR}/etc/systemd/system/kiosk.service"

# ---- sysctl and modprobe config ---------------------------------------------
install -m 644 files/etc/sysctl.d/99-beerpro.conf \
    "${ROOTFS_DIR}/etc/sysctl.d/99-beerpro.conf"
install -m 644 files/etc/modprobe.d/watchdog.conf \
    "${ROOTFS_DIR}/etc/modprobe.d/watchdog.conf"
