#!/usr/bin/env bash
# Setup script for macOS — equivalent of setup-all-services.ps1
# Installs YoutubeDownloader, NgrokTunnel, and GitHubActionsRunner as LaunchAgents
# (auto-start on login, restart on crash)
#
# Run as your normal user — no sudo needed.
# Usage: bash scripts/setup-mac.sh

set -euo pipefail

PROJECT_DIR="$HOME/dev/Youtube-Downloader"
RUNNER_DIR="$HOME/actions-runner"
NGROK_DOMAIN="nonimpregnated-georgine-thetically.ngrok-free.dev"
SERVER_PORT=8001
LOG_DIR="$PROJECT_DIR/logs"
PLIST_DIR="$HOME/Library/LaunchAgents"

# ── Detect executables ───────────────────────────────────────────────────────
PYTHON=$(command -v python3) || { echo "ERROR: python3 not found. Install via Homebrew: brew install python"; exit 1; }
NGROK=$(command -v ngrok)   || { echo "ERROR: ngrok not found. Install via Homebrew: brew install ngrok/ngrok/ngrok"; exit 1; }

echo "Python: $PYTHON"
echo "Ngrok:  $NGROK"
echo ""

# ── Create directories ───────────────────────────────────────────────────────
mkdir -p "$LOG_DIR" "$PLIST_DIR"

# ── Install Python dependencies ──────────────────────────────────────────────
echo "=== Installing Python dependencies ==="
pip3 install -r "$PROJECT_DIR/requirements.txt"
echo ""

# helper: unload a plist if it's loaded, ignoring errors
unload_if_loaded() {
    launchctl unload "$1" 2>/dev/null || true
}

# ── 1. YoutubeDownloader ─────────────────────────────────────────────────────
echo "=== Installing YoutubeDownloader LaunchAgent ==="
PLIST="$PLIST_DIR/com.youdescribe.youtube-downloader.plist"
unload_if_loaded "$PLIST"

PYTHON_BIN_DIR=$(dirname "$PYTHON")

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.youdescribe.youtube-downloader</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$PROJECT_DIR/server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$PYTHON_BIN_DIR:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/service-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/service-stderr.log</string>
</dict>
</plist>
EOF

launchctl load "$PLIST"
echo "YoutubeDownloader done."

# ── 2. NgrokTunnel ───────────────────────────────────────────────────────────
echo ""
echo "=== Installing NgrokTunnel LaunchAgent ==="
PLIST="$PLIST_DIR/com.youdescribe.ngrok.plist"
unload_if_loaded "$PLIST"

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.youdescribe.ngrok</string>
    <key>ProgramArguments</key>
    <array>
        <string>$NGROK</string>
        <string>http</string>
        <string>--url=$NGROK_DOMAIN</string>
        <string>$SERVER_PORT</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/ngrok-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/ngrok-stderr.log</string>
</dict>
</plist>
EOF

launchctl load "$PLIST"
echo "NgrokTunnel done."

# ── 3. GitHubActionsRunner ───────────────────────────────────────────────────
echo ""
echo "=== Installing GitHubActionsRunner LaunchAgent ==="
if [[ ! -f "$RUNNER_DIR/run.sh" ]]; then
    echo "SKIPPED: $RUNNER_DIR/run.sh not found."
    echo ""
    echo "  Set up the runner first, then re-run this script:"
    echo ""
    echo "    mkdir -p ~/actions-runner && cd ~/actions-runner"
    echo "    # Download the latest macOS runner from:"
    echo "    #   https://github.com/actions/runner/releases"
    echo "    # e.g. (Apple Silicon):"
    echo "    #   curl -O -L https://github.com/actions/runner/releases/download/v2.x.x/actions-runner-osx-arm64-2.x.x.tar.gz"
    echo "    #   tar xzf actions-runner-osx-arm64-*.tar.gz"
    echo "    # e.g. (Intel):"
    echo "    #   curl -O -L https://github.com/actions/runner/releases/download/v2.x.x/actions-runner-osx-x64-2.x.x.tar.gz"
    echo "    #   tar xzf actions-runner-osx-x64-*.tar.gz"
    echo ""
    echo "    # Get a registration token:"
    echo "    gh api repos/serinaqin/Youtube-Downloader/actions/runners/registration-token --method POST --jq .token"
    echo ""
    echo "    ./config.sh --url https://github.com/serinaqin/Youtube-Downloader \\"
    echo "                --token <TOKEN> --name mac-runner --labels self-hosted,macOS --unattended"
else
    PLIST="$PLIST_DIR/com.youdescribe.actions-runner.plist"
    unload_if_loaded "$PLIST"

    cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.youdescribe.actions-runner</string>
    <key>ProgramArguments</key>
    <array>
        <string>$RUNNER_DIR/run.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$RUNNER_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/runner-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/runner-stderr.log</string>
</dict>
</plist>
EOF

    launchctl load "$PLIST"
    echo "GitHubActionsRunner done."
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Status ==="
launchctl list | grep com.youdescribe || echo "(no com.youdescribe services found — check errors above)"
echo ""
echo "Server:  http://localhost:$SERVER_PORT"
echo "Public:  https://$NGROK_DOMAIN"
echo ""
echo "Log files:"
echo "  $LOG_DIR/service-stdout.log  — server output"
echo "  $LOG_DIR/service-stderr.log  — server errors"
echo "  $LOG_DIR/ngrok-stdout.log    — ngrok output"
echo "  $LOG_DIR/ngrok-stderr.log    — ngrok errors"
echo "  $LOG_DIR/runner-stdout.log   — runner output"
echo "  $LOG_DIR/runner-stderr.log   — runner errors"
echo ""
echo "Verify:"
echo "  curl http://localhost:$SERVER_PORT/health"
echo "  curl http://localhost:4040/api/tunnels"
echo "  gh api repos/serinaqin/Youtube-Downloader/actions/runners --jq '.runners[]'"
