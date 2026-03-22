#!/bin/bash
# =============================================================================
# Beer Pro — Raspberry Pi AP+STA Setup Script
# =============================================================================
# Configures the Pi to run in simultaneous Access Point + Station (client) mode:
#   - AP:  "BeerPro-Setup" on 192.168.4.1  (always on, for initial phone setup)
#   - STA: joins the user's home WiFi after they complete the setup flow
#
# Run once as root on a fresh Raspberry Pi OS Lite install:
#   sudo bash scripts/setup_ap.sh
#
# Tested on: Raspberry Pi OS Lite (Bookworm / Bullseye), Pi 3B+, Pi 4
# =============================================================================

set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AP_SSID="BeerPro-Setup"
AP_IP="192.168.4.1"
AP_SUBNET="192.168.4.0/24"
AP_DHCP_START="192.168.4.10"
AP_DHCP_END="192.168.4.50"
AP_INTERFACE="uap0"        # Virtual AP interface — avoids conflicts with STA on wlan0
STA_INTERFACE="wlan0"

echo ""
echo "=============================="
echo "  Beer Pro — AP+STA Setup"
echo "=============================="
echo ""

# ---- Require root ----------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (sudo bash scripts/setup_ap.sh)"
    exit 1
fi

# ---- Install dependencies --------------------------------------------------
echo "[1/7] Installing hostapd, dnsmasq, iw..."
apt-get update -qq
apt-get install -y hostapd dnsmasq iw >/dev/null

# ---- Create virtual AP interface on boot via systemd-networkd --------------
echo "[2/7] Creating uap0 virtual interface service..."

cat > /etc/systemd/system/uap0.service << EOF
[Unit]
Description=Create uap0 virtual WiFi interface for Beer Pro AP
Before=hostapd.service
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/iw dev ${STA_INTERFACE} interface add ${AP_INTERFACE} type __ap
ExecStop=/sbin/iw dev ${AP_INTERFACE} del

[Install]
WantedBy=multi-user.target
EOF

systemctl enable uap0.service

# ---- Assign static IP to uap0 via dhcpcd -----------------------------------
echo "[3/7] Configuring static IP for ${AP_INTERFACE}..."

# Remove any existing uap0 block from dhcpcd.conf
sed -i '/^# BeerPro AP/,/^$/d' /etc/dhcpcd.conf

cat >> /etc/dhcpcd.conf << EOF

# BeerPro AP interface — static IP
interface ${AP_INTERFACE}
    static ip_address=${AP_IP}/24
    nohook wpa_supplicant
EOF

# ---- Configure hostapd ------------------------------------------------------
echo "[4/7] Configuring hostapd (AP SSID: ${AP_SSID})..."

cat > /etc/hostapd/hostapd.conf << EOF
# Beer Pro — hostapd configuration
interface=${AP_INTERFACE}
driver=nl80211
ssid=${AP_SSID}
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
# Open network — no password needed to connect for setup
wpa=0
EOF

# Point hostapd at the config file
sed -i 's|#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd

systemctl unmask hostapd
systemctl enable hostapd

# ---- Configure dnsmasq (DHCP for AP clients) --------------------------------
echo "[5/7] Configuring dnsmasq (DHCP for ${AP_SSID})..."

# Preserve original config
if [[ ! -f /etc/dnsmasq.conf.orig ]]; then
    cp /etc/dnsmasq.conf /etc/dnsmasq.conf.orig
fi

cat > /etc/dnsmasq.conf << EOF
# Beer Pro — dnsmasq configuration

# Only serve DHCP on the AP interface
interface=${AP_INTERFACE}
bind-interfaces

# DHCP range for phones connecting to BeerPro-Setup
dhcp-range=${AP_DHCP_START},${AP_DHCP_END},255.255.255.0,24h

# Redirect all DNS queries to this device (captive portal behaviour)
address=/#/${AP_IP}

# mDNS-style hostname for convenience
# (actual mDNS is handled by avahi-daemon — see step 6)
EOF

systemctl enable dnsmasq

# ---- Enable IP forwarding + NAT so AP clients share the STA connection ------
echo "[6/7] Enabling IP forwarding and NAT..."

# Persist IP forwarding
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
fi
sysctl -w net.ipv4.ip_forward=1 >/dev/null

# iptables NAT — persisted via rc.local
cat > /etc/rc.local << EOF
#!/bin/bash
# Beer Pro — NAT for AP+STA bridge
iptables -t nat -A POSTROUTING -o ${STA_INTERFACE} -j MASQUERADE
iptables -A FORWARD -i ${STA_INTERFACE} -o ${AP_INTERFACE} -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i ${AP_INTERFACE} -o ${STA_INTERFACE} -j ACCEPT
exit 0
EOF
chmod +x /etc/rc.local

# ---- Install avahi for beerpro.local mDNS hostname -------------------------
echo "[7/7] Installing avahi-daemon for beerpro.local..."
apt-get install -y avahi-daemon >/dev/null

# Set the mDNS hostname
raspi-config nonint do_hostname beerpro 2>/dev/null || hostnamectl set-hostname beerpro

systemctl enable avahi-daemon

# ---- Done ------------------------------------------------------------------
echo ""
echo "=============================="
echo "  Setup complete!"
echo "=============================="
echo ""
echo "  AP SSID : ${AP_SSID}"
echo "  AP IP   : ${AP_IP}"
echo "  mDNS    : beerpro.local"
echo ""
echo "  Reboot now for changes to take effect:"
echo "    sudo reboot"
echo ""
