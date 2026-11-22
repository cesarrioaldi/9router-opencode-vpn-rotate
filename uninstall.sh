#!/usr/bin/env bash
set -euo pipefail

LABEL="com.9router.opencode-vpn-rotate"
NINEROUTER_HOME="${NINEROUTER_HOME:-$HOME/.9router}"
NINEROUTER_HOME="${NINEROUTER_HOME/#\~/$HOME}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
rm -f "$PLIST" "$NINEROUTER_HOME/opencode-vpn-rotate.py"

echo "Removed $LABEL"
echo "Logs and state kept in $NINEROUTER_HOME/run"
