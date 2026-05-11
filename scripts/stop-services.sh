#!/usr/bin/env bash
# Stop all YouDescribe services
# Usage: bash ~/dev/Youtube-Downloader/scripts/stop-services.sh

UID_VAL=$(id -u)

echo "Stopping YouDescribe services..."

for s in youtube-downloader ngrok actions-runner caffeinate; do
    launchctl bootout gui/$UID_VAL/com.youdescribe.$s 2>/dev/null
    echo "  ✔ $s stopped"
done

echo ""
echo "Service status (should be empty):"
launchctl list | grep youdescribe || echo "  All services stopped."
