#!/usr/bin/env bash
#
# Build a .deb for Hands Off. The package installs the Python source under
# /opt/handsoff and pulls its runtime deps from apt (python3-evdev, python3-pyqt5),
# so no pip/venv is needed at install time.
#
set -euo pipefail

VERSION="$(grep -oP '^version = "\K[^"]+' pyproject.toml)"
ARCH="all"
HERE="$(cd "$(dirname "$0")" && pwd)"
PKG="handsoff_${VERSION}_${ARCH}"
BUILD="${HERE}/build/${PKG}"

echo ">> Building Hands Off ${VERSION}"
rm -rf "${HERE}/build"
mkdir -p "${BUILD}/DEBIAN"
mkdir -p "${BUILD}/opt/handsoff/handsoff"
mkdir -p "${BUILD}/usr/bin"
mkdir -p "${BUILD}/usr/share/applications"
mkdir -p "${BUILD}/etc/xdg/autostart"
mkdir -p "${BUILD}/usr/share/icons/hicolor/scalable/apps"

# --- application source ---
cp -r "${HERE}/handsoff/." "${BUILD}/opt/handsoff/handsoff/"

# --- launcher ---
cat > "${BUILD}/usr/bin/handsoff" <<'EOF'
#!/bin/sh
export PYTHONPATH="/opt/handsoff:${PYTHONPATH:-}"
exec python3 -m handsoff "$@"
EOF
chmod 755 "${BUILD}/usr/bin/handsoff"

# --- desktop + autostart + icon ---
cp "${HERE}/packaging/handsoff.desktop" "${BUILD}/usr/share/applications/handsoff.desktop"
cp "${HERE}/packaging/handsoff.desktop" "${BUILD}/etc/xdg/autostart/handsoff.desktop"
cp "${HERE}/handsoff/resources/handsoff.svg" "${BUILD}/usr/share/icons/hicolor/scalable/apps/handsoff.svg"

# --- control ---
cat > "${BUILD}/DEBIAN/control" <<EOF
Package: handsoff
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3, python3-evdev, python3-pyqt5, python3-pyqt5.qtsvg
Recommends: libnotify-bin, pipewire-bin | pulseaudio-utils
Maintainer: Daniel Rosehill <daniel@danielrosehill.co.il>
Description: Toddler-proof keyboard & mouse lock
 Instantly freeze the keyboard and mouse with a hot-key so a small child can
 mash the keys without reaching your applications. Unlock by typing a secret
 word or clicking the system-tray icon.
EOF

# --- postinst: add the installing user to the input group ---
cat > "${BUILD}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
    usermod -aG input "${SUDO_USER}" || true
    echo ">> Added ${SUDO_USER} to the 'input' group."
    echo ">> Log out and back in for Hands Off to gain input access."
fi
exit 0
EOF
chmod 755 "${BUILD}/DEBIAN/postinst"

# --- build ---
mkdir -p "${HERE}/dist"
dpkg-deb --root-owner-group --build "${BUILD}" "${HERE}/dist/${PKG}.deb"
echo ">> Built: dist/${PKG}.deb"
