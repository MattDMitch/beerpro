#!/bin/bash -e
# stageB/02-network/01-run.sh
# Configure AP+STA networking inside the chroot.
# Uses NetworkManager (standard on bookworm arm64) for the uap0 static IP.
on_chroot << EOF

# ---- hostapd: point at our config file --------------------------------------
# /etc/default/hostapd now exists after package install
sed -i 's|^#*DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' \
    /etc/default/hostapd

systemctl unmask hostapd
systemctl enable hostapd

# ---- dnsmasq ----------------------------------------------------------------
systemctl enable dnsmasq

# ---- avahi-daemon -----------------------------------------------------------
systemctl enable avahi-daemon

# ---- netfilter-persistent (loads iptables rules on boot) --------------------
systemctl enable netfilter-persistent

# ---- Static IP for uap0 via NetworkManager ----------------------------------
# Create a NetworkManager connection profile for the uap0 AP interface
mkdir -p /etc/NetworkManager/system-connections
cat > /etc/NetworkManager/system-connections/uap0-static.nmconnection << 'NMCONN'
[connection]
id=uap0-static
type=ethernet
interface-name=uap0
autoconnect=true

[ipv4]
method=manual
addresses=192.168.4.1/24

[ipv6]
method=disabled
NMCONN
chmod 600 /etc/NetworkManager/system-connections/uap0-static.nmconnection

# ---- hostname for avahi (beerpro.local) ------------------------------------
hostnamectl set-hostname beerpro 2>/dev/null || true

# ---- debconf for iptables-persistent (non-interactive) ---------------------
echo "iptables-persistent iptables-persistent/autosave_v4 boolean true" | debconf-set-selections
echo "iptables-persistent iptables-persistent/autosave_v6 boolean false" | debconf-set-selections

EOF
