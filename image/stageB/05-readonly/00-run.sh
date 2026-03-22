#!/bin/bash -e
# stageB/05-readonly/00-run.sh
# Copy overlay/readonly config files into rootfs

install -m 755 files/boot/firstboot.sh \
    "${ROOTFS_DIR}/boot/firstboot.sh"
