#!/usr/bin/env bash
# build-linux.sh — Build VinaStudio for Linux
#
# Produces:
#   dist/vinastudio-X.Y.Z-linux-amd64.tar.gz
#   dist/vinastudio_X.Y.Z_amd64.deb
#
# Prerequisites:
#   - Python 3.12 (on PATH)
#   - pnpm (for frontend build)
#   - rsvg-convert or cairosvg (for icon conversion)
#   - dpkg-deb (for .deb packaging)
#
# Usage:
#   bash packaging/ci/build-linux.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# 0. Detect Python 3.12
# ---------------------------------------------------------------------------
PYTHON=""
for candidate in python3.12 python3; do
    if command -v "$candidate" &>/dev/null; then
        version="$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")"
        if [ "$version" = "3.12" ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.12 is required but not found on PATH."
    exit 1
fi
echo "==> Using Python: $PYTHON ($($PYTHON --version))"

# ---------------------------------------------------------------------------
# 1. Read version from pyproject.toml
# ---------------------------------------------------------------------------
VERSION="$($PYTHON -c "
import re
with open('pyproject.toml') as f:
    m = re.search(r'^version\s*=\s*\"([^\"]+)\"', f.read(), re.M)
    print(m.group(1) if m else '0.0.0')
")"
echo "==> Building VinaStudio ${VERSION}"

# ---------------------------------------------------------------------------
# 2. Create clean virtual environment
# ---------------------------------------------------------------------------
VENV_DIR=".venv-build"
if [ -d "$VENV_DIR" ]; then
    echo "==> Removing old build venv"
    rm -rf "$VENV_DIR"
fi

echo "==> Creating virtual environment in ${VENV_DIR}"
"$PYTHON" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ---------------------------------------------------------------------------
# 3. Install Python dependencies + PyInstaller
# ---------------------------------------------------------------------------
echo "==> Installing Python dependencies"
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
pip install pyinstaller

# ---------------------------------------------------------------------------
# 4. Build frontend
# ---------------------------------------------------------------------------
echo "==> Building frontend"
python scripts/build_web.py

# ---------------------------------------------------------------------------
# 5. Run PyInstaller
# ---------------------------------------------------------------------------
echo "==> Running PyInstaller"
pyinstaller packaging/pyinstaller/vinastudio.spec --noconfirm --clean

# ---------------------------------------------------------------------------
# 6. Generate PNG icon from SVG (for .deb package)
# ---------------------------------------------------------------------------
echo "==> Generating PNG icon"
mkdir -p packaging/linux

if command -v rsvg-convert &>/dev/null; then
    rsvg-convert -w 512 -h 512 vinastudio/desktop/assets/icon.svg -o packaging/linux/vinastudio.png
elif command -v cairosvg &>/dev/null; then
    cairosvg vinastudio/desktop/assets/icon.svg -w 512 -o packaging/linux/vinastudio.png
else
    echo "WARNING: No SVG converter found (rsvg-convert or cairosvg). Skipping PNG generation."
    echo "         Install with: sudo apt-get install librsvg2-bin   OR   pip install cairosvg"
fi

# ---------------------------------------------------------------------------
# 7. Assemble .deb package
# ---------------------------------------------------------------------------
echo "==> Assembling .deb package"

DEB_ROOT="$(mktemp -d)"
trap 'rm -rf "$DEB_ROOT"' EXIT

DEB_PKG_DIR="${DEB_ROOT}/vinastudio_${VERSION}_amd64"
mkdir -p "${DEB_PKG_DIR}/opt/vinastudio"
mkdir -p "${DEB_PKG_DIR}/DEBIAN"

# Copy built application
cp -a dist/vinastudio/* "${DEB_PKG_DIR}/opt/vinastudio/"

# Copy desktop integration files
cp packaging/linux/vinastudio.desktop "${DEB_PKG_DIR}/opt/vinastudio/"
if [ -f packaging/linux/vinastudio.png ]; then
    mkdir -p "${DEB_PKG_DIR}/usr/share/icons/hicolor/512x512/apps"
    cp packaging/linux/vinastudio.png "${DEB_PKG_DIR}/usr/share/icons/hicolor/512x512/apps/vinastudio.png"
fi

# Copy debian control files, substituting version
mkdir -p "${DEB_PKG_DIR}/usr/share/applications"
cp packaging/linux/vinastudio.desktop "${DEB_PKG_DIR}/usr/share/applications/vinastudio.desktop"
sed "s/^Version:.*/Version: ${VERSION}/" packaging/linux/debian/control > "${DEB_PKG_DIR}/DEBIAN/control"
cp packaging/linux/debian/postinst "${DEB_PKG_DIR}/DEBIAN/postinst"
cp packaging/linux/debian/prerm "${DEB_PKG_DIR}/DEBIAN/prerm"
chmod 755 "${DEB_PKG_DIR}/DEBIAN/postinst" "${DEB_PKG_DIR}/DEBIAN/prerm"

dpkg-deb --build "${DEB_PKG_DIR}" "dist/vinastudio_${VERSION}_amd64.deb"

# ---------------------------------------------------------------------------
# 8. Create tarball
# ---------------------------------------------------------------------------
echo "==> Creating tarball"
tar -czf "dist/vinastudio-${VERSION}-linux-amd64.tar.gz" -C dist vinastudio/

# ---------------------------------------------------------------------------
# 9. Summary
# ---------------------------------------------------------------------------
echo ""
echo "==> Build complete!"
echo "    dist/vinastudio-${VERSION}-linux-amd64.tar.gz"
echo "    dist/vinastudio_${VERSION}_amd64.deb"
echo ""

deactivate
