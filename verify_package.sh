#!/bin/bash
# Verification harness for the packaged Usage Status.app (goal plan).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRATCH="${SCRATCH:-/var/folders/qw/73l6rk954ng44379m5qdd8x00000gn/T/grok-goal-0c33730aecd0/implementer}"
APP_PATH="$ROOT/dist/Usage Status.app"
EXEC_PATH="$APP_PATH/Contents/MacOS/usage-status"
DMG_PATH="$ROOT/dist/Usage-Status.dmg"

mkdir -p "$SCRATCH"

echo "==> 1. Bundle structure"
test -d "$APP_PATH"
test -x "$EXEC_PATH"
file "$EXEC_PATH" | tee "$SCRATCH/executable-file.txt" | grep -q "Mach-O"
test -d "$APP_PATH/Contents/Resources/assets"
plutil -p "$APP_PATH/Contents/Info.plist" | tee "$SCRATCH/info-plist.txt" | grep -q "LSUIElement"
plutil -p "$APP_PATH/Contents/Info.plist" | grep -q "13.0"

echo "==> 2. --list (twice)"
"$EXEC_PATH" --list | tee "$SCRATCH/usage-list-run1.txt"
"$EXEC_PATH" --list | tee "$SCRATCH/usage-list-run2.txt"
grep -q "provider\tstatus\tcolor" "$SCRATCH/usage-list-run1.txt"
grep -q "grok" "$SCRATCH/usage-list-run1.txt"
grep -q "codex" "$SCRATCH/usage-list-run1.txt"
grep -q "claude" "$SCRATCH/usage-list-run1.txt"
diff -u "$SCRATCH/usage-list-run1.txt" "$SCRATCH/usage-list-run2.txt" | tee "$SCRATCH/usage-list-diff.txt"

echo "==> 3. --probe (twice)"
"$EXEC_PATH" --probe 2>"$SCRATCH/usage-probe-run1.log"
"$EXEC_PATH" --probe 2>"$SCRATCH/usage-probe-run2.log"
grep -q "usage-status: probe complete" "$SCRATCH/usage-probe-run1.log"

echo "==> 4. Unit tests"
cd "$ROOT"
python3 -m unittest test_usage_logic.py test_usage_preferences.py test_usage_status.py -v 2>&1 | tee "$SCRATCH/unit-tests.log"

echo "==> 5. Relocatability"
RELOC="/var/folders/qw/73l6rk954ng44379m5qdd8x00000gn/T/grok-goal-0c33730aecd0/Usage-Status-Test.app"
rm -rf "$RELOC"
ditto "$APP_PATH" "$RELOC"
"$RELOC/Contents/MacOS/usage-status" --list | tee "$SCRATCH/usage-list-reloc.txt"
grep -q "provider\tstatus\tcolor" "$SCRATCH/usage-list-reloc.txt"
open -a "$RELOC" --args --no-hud
sleep 2
pgrep -fl "Usage-Status-Test.app" | tee "$SCRATCH/open-launch.txt" || true
pkill -f "Usage-Status-Test.app" 2>/dev/null || true

echo "==> 6. DMG"
test -f "$DMG_PATH"
MOUNT_DIR="$SCRATCH/dmg-mount"
mkdir -p "$MOUNT_DIR"
hdiutil attach "$DMG_PATH" -nobrowse -quiet -mountpoint "$MOUNT_DIR"
test -d "$MOUNT_DIR/Usage Status.app"
test -x "$MOUNT_DIR/Install Usage Status.command"
hdiutil detach "$MOUNT_DIR" -quiet

echo "==> All verification checks passed"
echo "Evidence saved under $SCRATCH"