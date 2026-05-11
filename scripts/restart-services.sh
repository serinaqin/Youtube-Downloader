#!/usr/bin/env bash
# Restart all YouDescribe services
# Usage: bash ~/dev/Youtube-Downloader/scripts/restart-services.sh

UID_VAL=$(id -u)
PLIST_DIR="$HOME/Library/LaunchAgents"
SERVICES=(youtube-downloader ngrok actions-runner caffeinate)

echo "Restarting YouDescribe services..."

for s in "${SERVICES[@]}"; do
    LABEL="com.youdescribe.$s"
    PLIST="$PLIST_DIR/$LABEL.plist"

    if launchctl list "$LABEL" &>/dev/null; then
        launchctl kickstart -k gui/$UID_VAL/$LABEL
    else
        launchctl bootstrap gui/$UID_VAL "$PLIST"
    fi
    echo "  ✔ $s started"
done

sleep 2

# Verify
echo ""
echo "Service status:"
launchctl list | grep youdescribe
echo ""
curl -s http://localhost:8001/health && echo ""
