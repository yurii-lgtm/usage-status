#!/bin/bash
# Build a relocatable Usage Status.app and distributable DMG.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

echo "==> Installing build dependencies"
"$PYTHON" -m pip install --quiet --upgrade pip setuptools wheel py2app pyobjc-framework-Cocoa

echo "==> Cleaning previous build artifacts"
rm -rf build dist

echo "==> Building standalone app"
"$PYTHON" setup.py py2app

APP_PATH="dist/Usage Status.app"
EXEC_PATH="$APP_PATH/Contents/MacOS/usage-status"

if [[ ! -d "$APP_PATH" ]]; then
  echo "error: expected $APP_PATH after py2app build" >&2
  exit 1
fi

BUILT="$(find "$APP_PATH/Contents/MacOS" -maxdepth 1 -type f ! -name 'python' ! -name 'usage-status' | head -1)"
if [[ -n "$BUILT" && "$BUILT" != "$EXEC_PATH" ]]; then
  mv "$BUILT" "$EXEC_PATH"
fi

if [[ ! -x "$EXEC_PATH" ]]; then
  echo "error: missing executable at $EXEC_PATH" >&2
  exit 1
fi

/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable usage-status" "$APP_PATH/Contents/Info.plist"

if [[ ! -d "$APP_PATH/Contents/Resources/assets" ]]; then
  echo "error: bundled assets missing at Contents/Resources/assets" >&2
  exit 1
fi

echo "==> Creating DMG"
DMG_PATH="dist/Usage-Status.dmg"
STAGE="$ROOT/build/dmg-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
ditto "$APP_PATH" "$STAGE/Usage Status.app"
cat >"$STAGE/Install Usage Status.command" <<'EOF'
#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="/Applications/Usage Status.app"
rm -rf "$TARGET"
ditto "$DIR/Usage Status.app" "$TARGET"
osascript -e 'display notification "Usage Status is ready in Applications." with title "Usage Status Installed"'
open -a "$TARGET"
EOF
chmod +x "$STAGE/Install Usage Status.command"
rm -f "$DMG_PATH"
hdiutil create \
  -volname "Usage Status" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$DMG_PATH" >/dev/null

echo "==> Done"
echo "App: $APP_PATH"
echo "DMG: $DMG_PATH"