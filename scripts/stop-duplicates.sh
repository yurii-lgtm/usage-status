#!/bin/bash
# Stop all Usage Status copies so only one menu bar instance can run.
set -euo pipefail

echo "Stopping dev LaunchAgent (if loaded)..."
launchctl bootout "gui/$(id -u)/com.bot.usage-status" 2>/dev/null || true

echo "Stopping running Usage Status processes..."
pkill -x "usage-status" 2>/dev/null || true
pkill -f "usage_status.py" 2>/dev/null || true

LOCK="$HOME/Library/Application Support/com.bot.usage-status/instance.lock"
rm -f "$LOCK"

sleep 1
if pgrep -fl "usage-status|usage_status.py" >/dev/null 2>&1; then
  echo "Some processes may still be running:"
  pgrep -fl "usage-status|usage_status.py" || true
  exit 1
fi

echo "Done. Launch Usage Status once from Applications."