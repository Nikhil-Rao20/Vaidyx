#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/vaidyx-ui.service"

if [ ! -f "$SERVICE_FILE" ]; then
  echo "Error: vaidyx-ui.service not found in $SCRIPT_DIR"
  exit 1
fi

echo "Installing Vaidyx UI service..."
echo "Make sure you've edited vaidyx-ui.service with your username and paths first!"
echo ""

sudo cp "$SERVICE_FILE" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vaidyx-ui
sudo systemctl start vaidyx-ui
sudo systemctl status vaidyx-ui
