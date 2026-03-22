#!/bin/bash -e
# stageB prerun — copy stage2 (Raspberry Pi OS Lite) rootfs as our starting point.
#
# We explicitly reference stage2 because stage3/4/5 are skipped (SKIP file),
# which means PREV_ROOTFS_DIR points at a non-existent skipped stage.
# Pointing directly at stage2 is safe and reproducible.

STAGE2_ROOTFS="${WORK_DIR}/stage2/rootfs"

if [ ! -d "${STAGE2_ROOTFS}" ]; then
    echo "ERROR: stage2 rootfs not found at ${STAGE2_ROOTFS}"
    echo "       Make sure stage2 completed successfully."
    exit 1
fi

if [ ! -d "${ROOTFS_DIR}" ]; then
    echo "Copying stage2 rootfs to stageB..."
    mkdir -p "${ROOTFS_DIR}"
    rsync -aHAXx --exclude var/cache/apt/archives "${STAGE2_ROOTFS}/" "${ROOTFS_DIR}/"
fi
