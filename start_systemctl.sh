#!/bin/bash

# Exit on error
set -e

# Copy service files
sudo cp systemd/grib_parse.service /etc/systemd/system/
sudo cp systemd/grib_parse.timer /etc/systemd/system/

# Reload systemd and start service
sudo systemctl daemon-reload
sudo systemctl enable grib_parse.timer
sudo systemctl start grib_parse.timer

# Verify status
echo "Checking service status..."
sudo systemctl status grib_parse.timer

echo "Current timers: "
sudo systemctl list-timers --all

