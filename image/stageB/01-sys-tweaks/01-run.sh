#!/bin/bash -e
# stageB/01-sys-tweaks/01-run.sh
# Configure the rootfs after service files have been installed
on_chroot << EOF

# ---- Hostname ----------------------------------------------------------------
echo "beerpro" > /etc/hostname
sed -i 's/127\.0\.1\.1.*/127.0.1.1\tbeerpro/' /etc/hosts || \
    echo "127.0.1.1 beerpro" >> /etc/hosts

# ---- Timezone ----------------------------------------------------------------
ln -sf /usr/share/zoneinfo/America/New_York /etc/localtime
echo "America/New_York" > /etc/timezone
dpkg-reconfigure -f noninteractive tzdata

# ---- Locale ------------------------------------------------------------------
sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
locale-gen
update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

# ---- Disable SSH -------------------------------------------------------------
systemctl disable ssh 2>/dev/null || true

# ---- Hardware watchdog kernel module ----------------------------------------
grep -q "bcm2835_wdt" /etc/modules || echo "bcm2835_wdt" >> /etc/modules

# ---- Disable swap (reduces SD card wear) ------------------------------------
systemctl disable dphys-swapfile 2>/dev/null || true

# ---- Enable systemd services ------------------------------------------------
systemctl enable uap0.service
systemctl enable beerpro.service
systemctl enable kiosk.service

# ---- Sudoers: allow pi to restart beerpro without password ------------------
echo "pi ALL=(ALL) NOPASSWD: /bin/systemctl restart beerpro" \
    > /etc/sudoers.d/beerpro-restart
chmod 440 /etc/sudoers.d/beerpro-restart

# ---- Quiet boot -------------------------------------------------------------
if [ -f /boot/cmdline.txt ]; then
    # Remove existing console=tty1 (we'll add our own)
    sed -i 's/ console=tty1//' /boot/cmdline.txt || true
    # Add quiet boot params if not already present
    grep -q "quiet" /boot/cmdline.txt || \
        sed -i 's/$/ quiet loglevel=3 logo.nologo vt.global_cursor_default=0/' \
        /boot/cmdline.txt
fi

EOF
