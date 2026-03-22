# update_manager.py — OTA software update system
#
# Flow:
#   1. User pastes a URL into the Settings page pointing to a .zip archive
#   2. check_update(url)  — downloads manifest.json from <url>.manifest or
#                           reads manifest.json inside the zip (headers-only fetch)
#   3. apply_update(url)  — downloads zip, verifies SHA256, backs up current app,
#                           extracts new files, re-installs pip deps, restarts service
#   4. rollback()         — restores the most recent backup
#
# Update zip structure expected:
#   manifest.json
#   *.py  (top-level app files)
#   static/
#   requirements.txt
#
# manifest.json format:
#   { "version": "1.2.0", "sha256": "<hex>", "changelog": "..." }
#
# The zip MUST NOT contain system config files (hostapd, dnsmasq, etc.).
# Only .py files, static/, and requirements.txt are ever replaced.

import hashlib
import json
import logging
import os
import shutil
import ssl
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APP_DIR      = Path(__file__).parent.resolve()
VERSION_FILE = APP_DIR / "VERSION"
DATA_DIR     = Path("/data") if Path("/data").is_mount() else APP_DIR
BACKUP_DIR   = DATA_DIR / "backups" / "beerpro-prev"
VENV_PIP     = APP_DIR / ".venv" / "bin" / "pip"

# Files/dirs allowed to be replaced by an update (whitelist)
ALLOWED_UPDATE_PATHS = {
    "main.py", "server.py", "camera.py", "config.py",
    "game_state.py", "input_handler.py", "wifi_manager.py",
    "update_manager.py", "requirements.txt", "VERSION",
    "static",
}

# ---------------------------------------------------------------------------
# SSL context
# ---------------------------------------------------------------------------

def _make_ssl_context() -> ssl.SSLContext:
    """
    Return an SSL context that verifies certificates.

    Tries certifi's CA bundle first (pip-installed, always up-to-date).
    Falls back to the system CA store if certifi is not installed.
    This fixes 'certificate verify failed' on fresh Pi OS installs where
    the system CA store may be missing or outdated.
    """
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        logger.debug("SSL: using certifi CA bundle")
        return ctx
    except ImportError:
        pass
    ctx = ssl.create_default_context()
    logger.debug("SSL: using system CA store")
    return ctx


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def get_current_version() -> str:
    """Read VERSION file. Returns '0.0.0' if not found."""
    try:
        return VERSION_FILE.read_text().strip()
    except Exception:
        return "0.0.0"


def _version_tuple(v: str):
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0, 0, 0)


# ---------------------------------------------------------------------------
# Check update — fetch manifest only
# ---------------------------------------------------------------------------

def check_update(url: str) -> dict:
    """
    Fetch the manifest from the given URL.

    Tries two manifest URL conventions:
      1. <url>.manifest  (e.g. .../beerpro-v1.2.zip.manifest)
      2. <url> itself is the manifest JSON (for simple hosting)

    Returns:
      { ok, current_version, new_version, changelog, sha256, error }
    """
    current = get_current_version()

    ssl_ctx = _make_ssl_context()

    # Try <url>.manifest first, then the URL itself
    for manifest_url in [url.rstrip("/") + ".manifest", url]:
        try:
            logger.info(f"Fetching manifest from {manifest_url}")
            with urllib.request.urlopen(manifest_url, timeout=15, context=ssl_ctx) as resp:
                raw = resp.read(65536)  # 64KB max for manifest
            manifest = json.loads(raw)
            if "version" not in manifest:
                continue
            return {
                "ok": True,
                "current_version": current,
                "new_version": manifest["version"],
                "changelog": manifest.get("changelog", ""),
                "sha256": manifest.get("sha256", ""),
                "error": "",
                "is_newer": _version_tuple(manifest["version"]) > _version_tuple(current),
            }
        except json.JSONDecodeError:
            continue
        except Exception as e:
            logger.warning(f"Manifest fetch failed for {manifest_url}: {e}")
            continue

    return {
        "ok": False,
        "current_version": current,
        "new_version": "",
        "changelog": "",
        "sha256": "",
        "error": "Could not fetch update manifest. Check the URL.",
        "is_newer": False,
    }


# ---------------------------------------------------------------------------
# Apply update
# ---------------------------------------------------------------------------

def apply_update(url: str, progress_cb=None) -> dict:
    """
    Download, verify, backup, extract, reinstall deps, and restart.

    progress_cb(stage: str, pct: int) is called at each stage so the
    server can broadcast progress over WebSocket.

    Returns { ok, version, error }
    """
    def _progress(stage, pct):
        logger.info(f"Update [{pct}%] {stage}")
        if progress_cb:
            progress_cb(stage, pct)

    try:
        # ---- 1. Check manifest ------------------------------------------------
        _progress("Checking update info…", 5)
        manifest_info = check_update(url)
        if not manifest_info["ok"]:
            return {"ok": False, "version": "", "error": manifest_info["error"]}

        expected_sha256 = manifest_info["sha256"]
        new_version     = manifest_info["new_version"]

        # ---- 2. Download zip --------------------------------------------------
        _progress(f"Downloading v{new_version}…", 15)
        tmp_dir = Path(tempfile.mkdtemp(prefix="beerpro-update-"))
        zip_path = tmp_dir / "update.zip"

        try:
            ssl_ctx = _make_ssl_context()
            req = urllib.request.Request(url, headers={"User-Agent": "BeerPro-Updater/1.0"})
            with urllib.request.urlopen(req, timeout=60, context=ssl_ctx) as resp, \
                 open(zip_path, "wb") as out:
                shutil.copyfileobj(resp, out)
        except Exception as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {"ok": False, "version": "", "error": f"Download failed: {e}"}

        # ---- 3. Verify SHA256 -------------------------------------------------
        _progress("Verifying integrity…", 40)
        if expected_sha256:
            actual_sha256 = _sha256(zip_path)
            if actual_sha256 != expected_sha256.lower():
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return {
                    "ok": False,
                    "version": "",
                    "error": f"SHA256 mismatch — download may be corrupted. "
                             f"Expected {expected_sha256[:16]}… got {actual_sha256[:16]}…",
                }

        # ---- 4. Validate zip contents -----------------------------------------
        _progress("Validating package…", 50)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                _validate_zip_contents(names)
        except zipfile.BadZipFile:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {"ok": False, "version": "", "error": "Update file is not a valid zip archive."}
        except ValueError as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {"ok": False, "version": "", "error": str(e)}

        # ---- 5. Backup current app --------------------------------------------
        _progress("Backing up current version…", 60)
        _backup_current()

        # ---- 6. Extract new files ---------------------------------------------
        _progress("Installing new files…", 70)
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                _safe_extract(zf, member, APP_DIR)

        # ---- 7. Reinstall Python dependencies if requirements.txt changed -----
        _progress("Updating dependencies…", 85)
        req_file = APP_DIR / "requirements.txt"
        if req_file.exists() and VENV_PIP.exists():
            subprocess.run(
                [str(VENV_PIP), "install", "-q", "-r", str(req_file)],
                check=False, timeout=120
            )

        # ---- 8. Clean up temp dir ---------------------------------------------
        shutil.rmtree(tmp_dir, ignore_errors=True)

        _progress("Restarting service…", 95)

        # ---- 9. Restart beerpro service ---------------------------------------
        # Runs in a background thread with a short delay so the HTTP response
        # is sent back to the client before the process exits
        import threading
        def _restart():
            import time
            time.sleep(2)
            try:
                subprocess.run(
                    ["sudo", "systemctl", "restart", "beerpro"],
                    check=False, timeout=10
                )
            except Exception as e:
                logger.error(f"Service restart failed: {e}")

        threading.Thread(target=_restart, daemon=True).start()

        _progress("Done!", 100)
        return {"ok": True, "version": new_version, "error": ""}

    except Exception as e:
        logger.exception("Unexpected error during update")
        return {"ok": False, "version": "", "error": f"Unexpected error: {e}"}


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def rollback() -> dict:
    """Restore the previous backup."""
    if not BACKUP_DIR.exists():
        return {"ok": False, "error": "No backup found to roll back to."}

    try:
        for item in BACKUP_DIR.iterdir():
            dest = APP_DIR / item.name
            if dest.is_dir():
                shutil.rmtree(dest)
            elif dest.exists():
                dest.unlink()
            shutil.copy2(item, dest) if item.is_file() else shutil.copytree(item, dest)

        logger.info("Rollback complete")

        import threading, time
        def _restart():
            time.sleep(2)
            subprocess.run(["sudo", "systemctl", "restart", "beerpro"], check=False, timeout=10)
        threading.Thread(target=_restart, daemon=True).start()

        return {"ok": True, "error": ""}
    except Exception as e:
        logger.exception("Rollback failed")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_zip_contents(names: list) -> None:
    """
    Reject zips that try to write outside the app directory (path traversal)
    or touch system files.
    """
    for name in names:
        # Block absolute paths and traversal
        if name.startswith("/") or ".." in name:
            raise ValueError(f"Unsafe path in update archive: {name}")

        # Block anything not in the whitelist
        top = name.split("/")[0]
        if top and top not in ALLOWED_UPDATE_PATHS and top != "manifest.json":
            raise ValueError(
                f"Update archive contains unexpected path '{name}'. "
                "Only app .py files, static/, and requirements.txt are allowed."
            )


def _backup_current() -> None:
    """Copy current app files to BACKUP_DIR."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    # Clear previous backup
    shutil.rmtree(BACKUP_DIR, ignore_errors=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    for name in ALLOWED_UPDATE_PATHS:
        src = APP_DIR / name
        if not src.exists():
            continue
        dst = BACKUP_DIR / name
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def _safe_extract(zf: zipfile.ZipFile, member: zipfile.ZipInfo, dest_dir: Path) -> None:
    """Extract a single zip member, only if it's in the whitelist."""
    name = member.filename
    if name.endswith("/"):
        return  # directory entry

    top = name.split("/")[0]
    if top not in ALLOWED_UPDATE_PATHS and name != "manifest.json":
        return  # skip non-whitelisted files silently

    dest_path = dest_dir / name
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with zf.open(member) as src, open(dest_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
