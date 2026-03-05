#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# setup_launchd.sh
#
# Installs a macOS launchd job that runs daily_collect.py every day
# at 08:00 AM local time.
#
# Usage:
#   bash scripts/setup_launchd.sh          # install
#   bash scripts/setup_launchd.sh uninstall  # remove
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

LABEL="com.polymarket.daily-collect"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(which python3)"
LOG_DIR="${REPO_DIR}/logs"

mkdir -p "$LOG_DIR"

# ── Uninstall ─────────────────────────────────────────────────────
if [[ "${1:-}" == "uninstall" ]]; then
    if launchctl list | grep -q "$LABEL"; then
        launchctl unload "$PLIST" 2>/dev/null || true
        echo "Unloaded $LABEL"
    fi
    rm -f "$PLIST"
    echo "Removed $PLIST"
    exit 0
fi

# ── Install ───────────────────────────────────────────────────────
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>${REPO_DIR}/scripts/daily_collect.py</string>
    </array>

    <!-- Run every day at 08:00 AM -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>WorkingDirectory</key>
    <string>${REPO_DIR}</string>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/daily_collect.log</string>

    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/daily_collect_error.log</string>

    <!-- Re-run if missed while machine was off -->
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "✓ Installed: $LABEL"
echo "  Runs every day at 08:00 AM"
echo "  Logs → ${LOG_DIR}/daily_collect.log"
echo ""
echo "  To run once right now:"
echo "    python ${REPO_DIR}/scripts/daily_collect.py"
echo ""
echo "  To check it's loaded:"
echo "    launchctl list | grep polymarket"
echo ""
echo "  To uninstall:"
echo "    bash ${REPO_DIR}/scripts/setup_launchd.sh uninstall"
