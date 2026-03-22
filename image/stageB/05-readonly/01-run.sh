#!/bin/bash -e
# stageB/05-readonly/01-run.sh
# Configure read-only overlay filesystem and first-boot /data partition script
on_chroot << EOF

# ---- Install overlayroot ----------------------------------------------------
apt-get install -y overlayroot --quiet 2>/dev/null || true

cat > /etc/overlayroot.conf << 'OVERLAYCONF'
overlayroot="tmpfs:swap=0,recurse=0"
overlayroot_cfgdisk="disabled"
OVERLAYCONF

# ---- Install first-boot script as a one-shot systemd service ----------------
cat > /etc/systemd/system/beerpro-firstboot.service << 'FBSVC'
[Unit]
Description=Beer Pro First Boot Setup (creates /data partition)
After=local-fs.target
Before=beerpro.service
ConditionPathExists=/boot/firstboot.sh

[Service]
Type=oneshot
ExecStart=/bin/bash /boot/firstboot.sh
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
FBSVC

systemctl enable beerpro-firstboot.service

# ---- fstab placeholder for /data (filled in by firstboot.sh) ---------------
grep -q "DATA_PARTITION_PLACEHOLDER" /etc/fstab || \
    echo "# DATA_PARTITION_PLACEHOLDER" >> /etc/fstab

EOF
