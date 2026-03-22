#!/bin/bash
# =============================================================================
# Beer Pro — First Boot Script
# =============================================================================
# Runs ONCE on the very first boot after flashing.
# Creates a small ext4 /data partition at the end of the SD card,
# mounts it at /data, and sets up the required directory structure.
#
# After completion, removes itself from init.d so it never runs again.
# =============================================================================

set -e

LOG="/var/log/beerpro-firstboot.log"
exec >> "$LOG" 2>&1

echo "=== Beer Pro First Boot: $(date) ==="

DISK="/dev/mmcblk0"
DATA_SIZE="512M"   # 512MB for wifi creds, logs, and update backups

# ---- Wait for disk to settle ------------------------------------------------
sleep 3

# ---- Expand root partition to fill available space (skip /data allocation) --
# Use raspi-config's built-in expand mechanism
if command -v raspi-config &>/dev/null; then
    raspi-config nonint do_expand_rootfs || true
fi

# ---- Create /data partition -------------------------------------------------
# Find the next available partition number
LAST_PART=$(parted -s "$DISK" print | awk '/^ [0-9]/{last=$1} END{print last}')
NEW_PART=$((LAST_PART + 1))

echo "Creating partition ${DISK}p${NEW_PART} (${DATA_SIZE})..."

# Get end of disk
DISK_END=$(parted -s "$DISK" unit MB print free | awk '/Free Space/{last=$2} END{print last}')
DATA_START=$(python3 -c "
end = '$DISK_END'.replace('MB','').strip()
start = float(end) - 512
print(f'{start:.0f}MB')
" 2>/dev/null || echo "")

if [[ -z "$DATA_START" ]]; then
    echo "WARNING: Could not calculate /data partition start. Skipping /data creation."
    # Fall back: use /tmp as data dir (non-persistent but functional)
    sed -i 's/# DATA_PARTITION_PLACEHOLDER/tmpfs \/data tmpfs defaults,noatime,size=64m 0 0/' \
        /etc/fstab
else
    parted -s "$DISK" mkpart primary ext4 "$DATA_START" "100%"
    partprobe "$DISK"
    sleep 2

    DATA_DEV="${DISK}p${NEW_PART}"
    mkfs.ext4 -L beerpro-data "$DATA_DEV"

    # Get UUID
    DATA_UUID=$(blkid -s UUID -o value "$DATA_DEV")
    echo "Created /data partition: UUID=$DATA_UUID"

    # Add to fstab
    sed -i "s|# DATA_PARTITION_PLACEHOLDER|UUID=$DATA_UUID /data ext4 defaults,noatime 0 2|" \
        /etc/fstab

    # Mount it now
    mkdir -p /data
    mount UUID="$DATA_UUID" /data
fi

# ---- Create directory structure in /data ------------------------------------
mkdir -p /data/backups/beerpro-prev
mkdir -p /data/logs
chown -R pi:pi /data

echo "=== First boot complete: $(date) ==="

# ---- Remove this script so it never runs again ------------------------------
update-rc.d firstboot remove 2>/dev/null || true
rm -f /etc/rc2.d/S02firstboot 2>/dev/null || true
# Don't delete /etc/init.d/firstboot itself — leave as audit trail

# Reboot to apply overlayroot properly
echo "Rebooting to activate read-only filesystem..."
sleep 2
reboot
