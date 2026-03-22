#!/bin/bash -e
# stageB/02-network/00-run.sh
# Copy network config files into rootfs

# ---- hostapd config ---------------------------------------------------------
mkdir -p "${ROOTFS_DIR}/etc/hostapd"
install -m 644 files/etc/hostapd/hostapd.conf \
    "${ROOTFS_DIR}/etc/hostapd/hostapd.conf"

# ---- dnsmasq config ---------------------------------------------------------
install -m 644 files/etc/dnsmasq.conf \
    "${ROOTFS_DIR}/etc/dnsmasq.conf"

# ---- iptables rules ---------------------------------------------------------
mkdir -p "${ROOTFS_DIR}/etc/iptables"
install -m 644 files/etc/iptables/rules.v4 \
    "${ROOTFS_DIR}/etc/iptables/rules.v4"
# Empty IPv6 rules file (required by iptables-persistent)
echo -e "*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\nCOMMIT" \
    > "${ROOTFS_DIR}/etc/iptables/rules.v6"
