#!/usr/bin/env bash
set -euo pipefail

LABEL="com.9router.opencode-vpn-rotate"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NINEROUTER_HOME="${NINEROUTER_HOME:-$HOME/.9router}"
NINEROUTER_HOME="${NINEROUTER_HOME/#\~/$HOME}"
PYTHON="${PYTHON:-/usr/bin/python3}"
SCRIPT="$NINEROUTER_HOME/opencode-vpn-rotate.py"
RUN_DIR="$NINEROUTER_HOME/run"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
MIN_INTERVAL="${OPENCODE_VPN_MIN_INTERVAL:-900}"
MAX_TRIES="${OPENCODE_VPN_MAX_TRIES:-1}"
LOG_PATH="${OPENCODE_VPN_LOG:-$RUN_DIR/gateway.log}"
LOG_PATH="${LOG_PATH/#\~/$HOME}"
API_URL="${OPENCODE_API_URL:-http://127.0.0.1:20130/v1/chat/completions}"
MODEL="${OPENCODE_MODEL:-oc}"
IP_TIMEOUT="${OPENCODE_VPN_IP_TIMEOUT:-45}"
COUNTRIES="${OPENCODE_VPN_COUNTRIES:-}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This watcher is macOS-only: it uses the NordVPN app and launchd." >&2
  exit 1
fi

if [[ ! -d "/Applications/NordVPN.app" ]]; then
  echo "NordVPN.app not found in /Applications. Install and sign in to NordVPN first." >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Python not found: $PYTHON" >&2
  exit 1
fi

mkdir -p "$RUN_DIR" "$HOME/Library/LaunchAgents"
cp "$REPO_DIR/opencode-vpn-rotate.py" "$SCRIPT"
chmod +x "$SCRIPT"
if [[ ! -f "$LOG_PATH" ]]; then
  echo "Warning: $LOG_PATH does not exist yet; the watcher will wait for it." >&2
fi
touch "$LOG_PATH" 2>/dev/null || true

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$SCRIPT</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ProcessType</key>
  <string>Background</string>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>StandardOutPath</key>
  <string>$RUN_DIR/opencode-vpn-rotate.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$RUN_DIR/opencode-vpn-rotate.stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>NINEROUTER_HOME</key>
    <string>$NINEROUTER_HOME</string>
    <key>OPENCODE_VPN_LOG</key>
    <string>$LOG_PATH</string>
    <key>OPENCODE_API_URL</key>
    <string>$API_URL</string>
    <key>OPENCODE_MODEL</key>
    <string>$MODEL</string>
    <key>OPENCODE_VPN_MIN_INTERVAL</key>
    <string>$MIN_INTERVAL</string>
    <key>OPENCODE_VPN_MAX_TRIES</key>
    <string>$MAX_TRIES</string>
    <key>OPENCODE_VPN_COUNTRIES</key>
    <string>$COUNTRIES</string>
    <key>OPENCODE_VPN_IP_TIMEOUT</key>
    <string>$IP_TIMEOUT</string>
    <key>PATH</key>
    <string>/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
EOF

plutil -lint "$PLIST" >/dev/null
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed $LABEL"
echo "  script: $SCRIPT"
echo "  log:    $RUN_DIR/opencode-vpn-rotate.log"
echo "  stop:   launchctl bootout gui/$(id -u) $PLIST"
