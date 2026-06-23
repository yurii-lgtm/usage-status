#!/bin/bash
# Sign and notarize Usage Status.app + DMG when Developer ID credentials are available.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_PATH="${APP_PATH:-$ROOT/dist/Usage Status.app}"
DMG_PATH="${DMG_PATH:-$ROOT/dist/Usage-Status.dmg}"
ZIP_PATH="${ZIP_PATH:-$ROOT/dist/Usage-Status-notarize.zip}"

SIGN_IDENTITY="${SIGN_IDENTITY:-}"
APPLE_ID="${APPLE_ID:-}"
APPLE_APP_PASSWORD="${APPLE_APP_PASSWORD:-${APPLE_APP_SPECIFIC_PASSWORD:-}}"
NOTARY_PROFILE="${NOTARY_PROFILE:-usage-status-notary}"

if [[ -z "$SIGN_IDENTITY" ]]; then
  SIGN_IDENTITY="$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application:.*\)".*/\1/p' | head -1)"
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "error: app not found at $APP_PATH (run ./package.sh first)" >&2
  exit 1
fi

if [[ -z "$SIGN_IDENTITY" ]]; then
  echo "warning: no Developer ID Application certificate found; skipping sign/notarize." >&2
  echo "Install a Developer ID cert from Apple Developer, then rerun:" >&2
  echo "  SIGN_IDENTITY='Developer ID Application: ...' APPLE_ID=you@email.com APPLE_APP_PASSWORD=xxxx ./scripts/notarize.sh" >&2
  exit 0
fi

echo "==> Signing app with: $SIGN_IDENTITY"
codesign --force --deep --options runtime --timestamp \
  --sign "$SIGN_IDENTITY" \
  "$APP_PATH"

echo "==> Verifying app signature"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
spctl --assess --type execute --verbose=4 "$APP_PATH" || true

echo "==> Preparing notarization zip"
rm -f "$ZIP_PATH"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

if [[ -z "$APPLE_ID" || -z "$APPLE_APP_PASSWORD" ]]; then
  echo "warning: APPLE_ID or APPLE_APP_PASSWORD not set; app is signed but not notarized." >&2
  echo "Create an app-specific password and rerun with both env vars set." >&2
  exit 0
fi

echo "==> Submitting for notarization"
if xcrun notarytool submit "$ZIP_PATH" --wait \
  --apple-id "$APPLE_ID" \
  --password "$APPLE_APP_PASSWORD" \
  --team-id "$(security find-identity -v -p codesigning | sed -n 's/.*(\([^)]*\)).*/\1/p' | head -1)" 2>/dev/null; then
  :
elif xcrun notarytool submit "$ZIP_PATH" --wait --keychain-profile "$NOTARY_PROFILE"; then
  :
else
  echo "error: notarization submit failed" >&2
  exit 1
fi

echo "==> Stapling ticket"
xcrun stapler staple "$APP_PATH"

if [[ -f "$DMG_PATH" ]]; then
  echo "==> Rebuilding signed DMG"
  STAGE="$ROOT/build/dmg-stage-signed"
  rm -rf "$STAGE"
  mkdir -p "$STAGE"
  ditto "$APP_PATH" "$STAGE/Usage Status.app"
  cp "$ROOT/build/dmg-stage/Install Usage Status.command" "$STAGE/" 2>/dev/null || true
  rm -f "$DMG_PATH"
  hdiutil create -volname "Usage Status" -srcfolder "$STAGE" -ov -format UDZO "$DMG_PATH" >/dev/null
  codesign --force --sign "$SIGN_IDENTITY" "$DMG_PATH"
  xcrun stapler staple "$DMG_PATH" || true
fi

echo "==> Notarization complete"