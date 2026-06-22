#!/usr/bin/env bash
# Build the app and (re)install it into /Applications, replacing any running copy.
# For local testing of the INSTALLED app — TCC (Full Disk Access) + the login-item
# LaunchAgent behave like a real install, unlike `npm start` dev mode. No DMG
# mount/drag needed.
#
#   ./scripts/dev-install.sh      (or: npm run reinstall)
#
# Note: an UNSIGNED app's Full-Disk-Access grant is keyed on its code hash, which
# changes every build — macOS may ask you to re-grant FDA after a reinstall. We
# rsync in place (same bundle path) to minimise that; a signed build wouldn't need it.
set -euo pipefail

cd "$(dirname "$0")/.."   # → desktop/
APP_NAME="llm-wiki"
DEST="/Applications/${APP_NAME}.app"

echo "▸ Building (npm run package)…"
if ! npm run package >/tmp/llm-wiki-package.log 2>&1; then
  echo "✗ build failed — last lines:"; tail -8 /tmp/llm-wiki-package.log; exit 1
fi

BUILT="$(find out -maxdepth 2 -name "${APP_NAME}.app" -type d | head -1)"
[ -n "$BUILT" ] || { echo "✗ built ${APP_NAME}.app not found under out/"; exit 1; }

echo "▸ Quitting running copy…"
osascript -e "tell application \"${APP_NAME}\" to quit" 2>/dev/null || true
pkill -f "${DEST}/Contents/MacOS/" 2>/dev/null || true
sleep 1

echo "▸ Installing → ${DEST}"
mkdir -p "${DEST}"
rsync -a --delete "${BUILT}/" "${DEST}/"   # in-place sync (no rm of the bundle)

echo "▸ Launching…"
open "${DEST}"
echo "✓ ${APP_NAME} reinstalled + launched ($(date +%H:%M:%S))"
