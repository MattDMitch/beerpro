# wifi_manager.py — WiFi scan, connect, and status management
#
# Uses wpa_cli + wpa_supplicant (standard on Raspberry Pi OS Lite).
# Falls back gracefully on non-Linux platforms (dev/macOS) so the app
# still runs without crashing.
#
# Credentials state is stored in wifi_credentials.json at the project root.
# The file records whether setup has been completed and which SSID was joined.
# The actual WPA passphrase is stored only inside wpa_supplicant's own config —
# never persisted here.

import json
import logging
import os
import re
import subprocess
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

# Use /data partition when available (read-only overlay-fs image),
# fall back to app directory for dev/non-image environments
_DATA_DIR = "/data" if os.path.ismount("/data") else os.path.dirname(__file__)
CREDENTIALS_FILE = os.path.join(_DATA_DIR, "wifi_credentials.json")
WPA_SUPPLICANT_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"
IS_LINUX = os.uname().sysname == "Linux" if hasattr(os, "uname") else False


# ---------------------------------------------------------------------------
# Credentials file helpers
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """Return True if wifi_credentials.json exists and marks setup as done."""
    if not os.path.exists(CREDENTIALS_FILE):
        return False
    try:
        with open(CREDENTIALS_FILE) as f:
            data = json.load(f)
        return bool(data.get("configured"))
    except Exception:
        return False


def _write_credentials(ssid: str, ip: str = "") -> None:
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump({"configured": True, "ssid": ssid, "ip": ip}, f, indent=2)


def forget() -> None:
    """Delete credentials file — forces setup mode on next boot."""
    if os.path.exists(CREDENTIALS_FILE):
        os.remove(CREDENTIALS_FILE)
    logger.info("WiFi credentials cleared — setup mode will activate on restart")


def saved_ssid() -> str:
    """Return the SSID from the credentials file, or empty string."""
    try:
        with open(CREDENTIALS_FILE) as f:
            return json.load(f).get("ssid", "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Network scan
# ---------------------------------------------------------------------------

def scan_networks() -> List[dict]:
    """
    Return a list of visible WiFi networks sorted by signal strength (desc).
    Each entry: { ssid, signal (0-100), secured (bool) }

    On non-Linux (dev mode) returns a mock list.
    """
    if not IS_LINUX:
        return _mock_networks()

    try:
        # Trigger a fresh scan
        subprocess.run(
            ["wpa_cli", "-i", "wlan0", "scan"],
            capture_output=True, timeout=5
        )
        time.sleep(2)  # Allow scan to complete

        result = subprocess.run(
            ["wpa_cli", "-i", "wlan0", "scan_results"],
            capture_output=True, text=True, timeout=5
        )
        return _parse_scan_results(result.stdout)
    except Exception as e:
        logger.warning(f"WiFi scan failed: {e}")
        return []


def _parse_scan_results(raw: str) -> List[dict]:
    """
    Parse wpa_cli scan_results output.
    Format: bssid / frequency / signal level / flags / ssid
    """
    networks = {}
    for line in raw.splitlines():
        # Skip header line
        if line.startswith("bssid") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        bssid, freq, signal_dbm, flags, ssid = parts[0], parts[1], parts[2], parts[3], "\t".join(parts[4:])
        ssid = ssid.strip()
        if not ssid or ssid == "\\x00":
            continue  # Hidden network — skip

        # Convert dBm to 0-100 signal percentage
        try:
            dbm = int(signal_dbm)
            # Typical range: -30 (excellent) to -90 (unusable)
            signal_pct = max(0, min(100, 2 * (dbm + 100)))
        except ValueError:
            signal_pct = 0

        secured = "WPA" in flags or "WEP" in flags

        # Deduplicate by SSID — keep strongest signal
        if ssid not in networks or signal_pct > networks[ssid]["signal"]:
            networks[ssid] = {"ssid": ssid, "signal": signal_pct, "secured": secured}

    # Sort by signal strength descending
    return sorted(networks.values(), key=lambda n: n["signal"], reverse=True)


def _mock_networks() -> List[dict]:
    """Dev-mode mock networks for testing on macOS/Windows."""
    return [
        {"ssid": "HomeNetwork",      "signal": 85, "secured": True},
        {"ssid": "Neighbour_5G",     "signal": 62, "secured": True},
        {"ssid": "CoffeeShop_Guest", "signal": 45, "secured": False},
        {"ssid": "BeerPro-Setup",    "signal": 99, "secured": False},
    ]


# ---------------------------------------------------------------------------
# Connect
# ---------------------------------------------------------------------------

def connect(ssid: str, password: str) -> dict:
    """
    Attempt to connect to a WiFi network.
    Returns { ok: bool, ip: str, error: str }

    On non-Linux (dev mode) always returns success with a mock IP.
    """
    if not IS_LINUX:
        logger.info(f"[DEV] Mock WiFi connect to '{ssid}'")
        _write_credentials(ssid, "192.168.1.42")
        return {"ok": True, "ip": "192.168.1.42", "error": ""}

    try:
        return _connect_wpa_cli(ssid, password)
    except Exception as e:
        logger.error(f"WiFi connect error: {e}")
        return {"ok": False, "ip": "", "error": str(e)}


def _connect_wpa_cli(ssid: str, password: str) -> dict:
    """Connect using wpa_cli commands."""

    def run(args, timeout=10):
        return subprocess.run(
            ["wpa_cli", "-i", "wlan0"] + args,
            capture_output=True, text=True, timeout=timeout
        )

    # Add new network
    result = run(["add_network"])
    if not result.stdout.strip().isdigit():
        return {"ok": False, "ip": "", "error": "Failed to add network profile"}
    net_id = result.stdout.strip()

    # Set SSID
    run(["set_network", net_id, "ssid", f'"{ssid}"'])

    # Set credentials
    if password:
        run(["set_network", net_id, "psk", f'"{password}"'])
    else:
        # Open network
        run(["set_network", net_id, "key_mgmt", "NONE"])

    # Disable all other networks and enable this one
    run(["select_network", net_id])

    # Wait for connection (up to 15 seconds)
    for _ in range(15):
        time.sleep(1)
        status = run(["status"])
        if "wpa_state=COMPLETED" in status.stdout:
            ip = _get_ip()
            if ip:
                # Persist config so it survives reboot
                run(["save_config"])
                _write_credentials(ssid, ip)
                logger.info(f"Connected to '{ssid}' with IP {ip}")
                return {"ok": True, "ip": ip, "error": ""}

    # Check if we got wrong password
    status = run(["status"])
    if "wpa_state=4WAY_HANDSHAKE" in status.stdout or "wpa_state=SCANNING" in status.stdout:
        # Remove the failed network profile
        run(["remove_network", net_id])
        run(["save_config"])
        return {"ok": False, "ip": "", "error": "Wrong password or network unreachable"}

    run(["remove_network", net_id])
    run(["save_config"])
    return {"ok": False, "ip": "", "error": "Connection timed out"}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def current_status() -> dict:
    """
    Return current WiFi status.
    { connected: bool, ssid: str, ip: str, ap_ssid: str }
    """
    ap_ssid = "BeerPro-Setup"

    if not IS_LINUX:
        if is_configured():
            return {
                "connected": True,
                "ssid": saved_ssid(),
                "ip": "192.168.1.42",
                "ap_ssid": ap_ssid,
            }
        return {"connected": False, "ssid": "", "ip": "", "ap_ssid": ap_ssid}

    try:
        result = subprocess.run(
            ["wpa_cli", "-i", "wlan0", "status"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout
        connected = "wpa_state=COMPLETED" in output

        ssid = ""
        m = re.search(r"^ssid=(.+)$", output, re.MULTILINE)
        if m:
            ssid = m.group(1).strip()

        ip = _get_ip()
        return {"connected": connected, "ssid": ssid, "ip": ip, "ap_ssid": ap_ssid}
    except Exception as e:
        logger.warning(f"WiFi status check failed: {e}")
        return {"connected": False, "ssid": "", "ip": "", "ap_ssid": ap_ssid}


def _get_ip() -> str:
    """Return the current IP address on wlan0, or empty string."""
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show", "wlan0"],
            capture_output=True, text=True, timeout=5
        )
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
        return m.group(1) if m else ""
    except Exception:
        return ""
