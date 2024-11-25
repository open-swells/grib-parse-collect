#!/bin/bash

# Variables
SERVICE_NAME="grib_parse"
SERVICE_FILE="$SERVICE_NAME.service"
TIMER_FILE="$SERVICE_NAME.timer"
SCRIPT_PATH="grib-parse.py"
SYSTEMD_PATH="/etc/systemd/system"
DEST_PATH="/usr/local/bin" # Location on the server for the Python script

echo "Copying files to the server..."
sudo cp "systemd/$SERVICE_FILE" "$SYSTEMD_PATH"
sudo cp "systemd/$TIMER_FILE" "$SYSTEMD_PATH"
sudo mkdir -p "$DEST_PATH"
sudo cp "$SCRIPT_PATH" "$DEST_PATH"

echo "Setting permissions..."
sudo chmod 644 "$SYSTEMD_PATH/$SERVICE_FILE"
sudo chmod 644 "$SYSTEMD_PATH/$TIMER_FILE"
sudo chmod +x "$DEST_PATH/$(basename $SCRIPT_PATH)"

echo "Reloading systemd and enabling the timer..."
sudo systemctl daemon-reload
sudo systemctl enable "$TIMER_FILE"
sudo systemctl start "$TIMER_FILE"

echo "Service and timer setup completed."

