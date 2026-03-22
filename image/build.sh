#!/bin/bash
# =============================================================================
# Beer Pro — pi-gen Docker Image Builder
# =============================================================================
# Produces: image/deploy/beerpro-v1.0-pi3bplus.img.xz
#
# Requirements:
#   - Docker Desktop running (Apple Silicon M1/M2/M3 or Intel Mac)
#
# Usage:
#   cd image && bash build.sh
#
# Options:
#   CLEAN=1 bash build.sh    — full clean build (30-40 min)
#   CLEAN=0 bash build.sh    — incremental build using Docker cache (~5-10 min)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIGEN_DIR="$SCRIPT_DIR/.pi-gen-build"
STAGE_DIR="$SCRIPT_DIR/stageB"
DEPLOY_DIR="$SCRIPT_DIR/deploy"
CLEAN="${CLEAN:-0}"

# Pin to a specific bookworm arm64 tag for reproducible builds
PIGEN_TAG="2025-05-13-raspios-bookworm-arm64"
PIGEN_REPO="https://github.com/RPi-Distro/pi-gen.git"

echo ""
echo "========================================"
echo "  Beer Pro — Image Builder"
echo "========================================"
echo "  App source : $APP_DIR"
echo "  pi-gen tag : $PIGEN_TAG"
echo "  Output     : $DEPLOY_DIR/"
echo "========================================"
echo ""

# ---- Check Docker is running ------------------------------------------------
if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker is not running. Start Docker Desktop and try again."
    exit 1
fi

# ---- Clone pi-gen at exact bookworm arm64 tag -------------------------------
if [[ ! -d "$PIGEN_DIR/.git" ]]; then
    echo "[1/6] Cloning pi-gen @ $PIGEN_TAG..."
    git clone --depth=1 --branch "$PIGEN_TAG" "$PIGEN_REPO" "$PIGEN_DIR"
else
    echo "[1/6] pi-gen already cloned — verifying tag..."
    CURRENT_TAG=$(git -C "$PIGEN_DIR" describe --tags 2>/dev/null || echo "unknown")
    if [[ "$CURRENT_TAG" != "$PIGEN_TAG" ]]; then
        echo "  Tag mismatch ($CURRENT_TAG vs $PIGEN_TAG) — re-cloning..."
        rm -rf "$PIGEN_DIR"
        git clone --depth=1 --branch "$PIGEN_TAG" "$PIGEN_REPO" "$PIGEN_DIR"
    else
        echo "  Already at $PIGEN_TAG — OK"
    fi
fi

# ---- Skip desktop stages (we only want Lite + stageB) -----------------------
echo "[2/6] Configuring pi-gen stages..."
# Skip building stage3/4/5 entirely — we only need Lite (stage2) + stageB
for stage in stage3 stage4 stage5; do
    [[ -d "$PIGEN_DIR/$stage" ]] && touch "$PIGEN_DIR/$stage/SKIP"
    # SKIP_IMAGES prevents these stages from being included in EXPORT_DIRS
    # even if they have an EXPORT_IMAGE file (stage4 does)
    [[ -d "$PIGEN_DIR/$stage" ]] && touch "$PIGEN_DIR/$stage/SKIP_IMAGES"
done
# Skip the stage2 image export — we export from stageB instead
[[ -d "$PIGEN_DIR/stage2" ]] && touch "$PIGEN_DIR/stage2/SKIP_IMAGES"

# ---- Sync current app source files into stageB/03-app/files ----------------
echo "[3/6] Syncing app source into stageB..."
APP_FILES_DIR="$STAGE_DIR/03-app/files/home/pi/beerpro"
mkdir -p "$APP_FILES_DIR/static" "$APP_FILES_DIR/scripts"

for f in main.py server.py camera.py config.py game_state.py \
          input_handler.py wifi_manager.py update_manager.py \
          requirements.txt VERSION; do
    if [[ -f "$APP_DIR/$f" ]]; then
        cp "$APP_DIR/$f" "$APP_FILES_DIR/$f"
        echo "    synced $f"
    else
        echo "    WARNING: $f not found in $APP_DIR"
    fi
done

for f in index.html app.js style.css; do
    if [[ -f "$APP_DIR/static/$f" ]]; then
        cp "$APP_DIR/static/$f" "$APP_FILES_DIR/static/$f"
        echo "    synced static/$f"
    fi
done

for f in kiosk.sh beerpro.service kiosk.service setup_ap.sh; do
    if [[ -f "$APP_DIR/scripts/$f" ]]; then
        cp "$APP_DIR/scripts/$f" "$APP_FILES_DIR/scripts/$f"
        echo "    synced scripts/$f"
    fi
done

# ---- Patch pi-gen: guard bmap copy (bmaptool not in build container) --------
# The finalise script unconditionally copies the .bmap file even if bmaptool
# wasn't available to create it, causing a build failure. Guard the copy.
# Guard matches only the original unguarded line so this is idempotent.
FINALISE_SCRIPT="$PIGEN_DIR/export-image/05-finalise/01-run.sh"
if [[ -f "$FINALISE_SCRIPT" ]] && grep -qx 'cp "\$BMAP_FILE" "\$DEPLOY_DIR/"' "$FINALISE_SCRIPT"; then
    # Use Python for portable in-place replacement (avoids macOS vs GNU sed differences)
    python3 -c "
import sys
path = sys.argv[1]
content = open(path).read()
content = content.replace(
    'cp \"\$BMAP_FILE\" \"\$DEPLOY_DIR/\"',
    '[ -f \"\$BMAP_FILE\" ] && cp \"\$BMAP_FILE\" \"\$DEPLOY_DIR/\" || true'
)
open(path, 'w').write(content)
" "$FINALISE_SCRIPT"
    echo "  Patched export-image/05-finalise/01-run.sh (bmap guard)"
fi

# ---- Patch pi-gen Dockerfile: fix platform for Apple Silicon / arm64 hosts --
# Without this, Docker on arm64 Macs pulls debian:bookworm as linux/arm/v7
# (32-bit), causing a platform mismatch warning and potential build failures.
DOCKERFILE="$PIGEN_DIR/Dockerfile"
if [[ -f "$DOCKERFILE" ]] && ! grep -q 'platform=linux/arm64' "$DOCKERFILE"; then
    python3 -c "
import sys
path = sys.argv[1]
content = open(path).read()
content = content.replace(
    'FROM \${BASE_IMAGE}',
    'FROM --platform=linux/arm64 \${BASE_IMAGE}'
)
open(path, 'w').write(content)
" "$DOCKERFILE"
    echo "  Patched Dockerfile (--platform=linux/arm64)"
fi

# ---- Install stageB into pi-gen directory -----------------------------------
echo "[4/6] Installing stageB into pi-gen..."
rm -rf "$PIGEN_DIR/stageB"
cp -r "$STAGE_DIR" "$PIGEN_DIR/stageB"
find "$PIGEN_DIR/stageB" -name "*.sh" -exec chmod +x {} \;
find "$PIGEN_DIR/stageB" -name "00-run*" -exec chmod +x {} \;

# Copy our config into pi-gen
cp "$SCRIPT_DIR/config" "$PIGEN_DIR/config"

# ---- Clean build if requested -----------------------------------------------
if [[ "$CLEAN" == "1" ]]; then
    echo "[5/6] Cleaning previous build artifacts..."
    rm -rf "$PIGEN_DIR/work" "$PIGEN_DIR/deploy"
    docker rm -f beerpro_pigen_work 2>/dev/null || true
else
    echo "[5/6] Incremental build (set CLEAN=1 to force full rebuild)"
fi

# ---- Run pi-gen Docker build ------------------------------------------------
echo "[6/6] Starting pi-gen Docker build..."
echo "      First run: ~30-40 minutes | With cache: ~5-10 minutes"
echo ""

cd "$PIGEN_DIR"
bash build-docker.sh

# ---- Copy output to image/deploy/ -------------------------------------------
mkdir -p "$DEPLOY_DIR"
BUILT_IMG=$(ls "$PIGEN_DIR/deploy/"*beerpro*.img.xz 2>/dev/null | head -1 || \
            ls "$PIGEN_DIR/deploy/"*.img.xz 2>/dev/null | head -1 || echo "")

if [[ -n "$BUILT_IMG" ]]; then
    cp "$BUILT_IMG" "$DEPLOY_DIR/"
    FINAL_IMG="$DEPLOY_DIR/$(basename "$BUILT_IMG")"
    echo ""
    echo "========================================"
    echo "  Build complete!"
    echo "========================================"
    echo ""
    ls -lh "$FINAL_IMG"
    echo ""
    echo "  Flash with Raspberry Pi Imager:"
    echo "    'Use custom image' → select $(basename "$FINAL_IMG")"
    echo ""
    echo "  Or via command line:"
    echo "    xz -d '$(basename "$FINAL_IMG")'"
    echo "    sudo dd if='$(basename "$FINAL_IMG" .xz)' of=/dev/sdX bs=4M status=progress"
    echo ""
else
    echo ""
    echo "ERROR: No .img.xz found in $PIGEN_DIR/deploy/"
    echo "Check the pi-gen Docker output above for errors."
    ls "$PIGEN_DIR/deploy/" 2>/dev/null || echo "(deploy directory is empty)"
    exit 1
fi
