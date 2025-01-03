#!/bin/bash

# Load environment variables from config file
# Define absolute paths
SCRIPT_DIR="/home/evan/grib-parse-collect"

# Source the .env file
if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
fi

# Path to the Python script with defaults
PYTHON_SCRIPT="${PYTHON_SCRIPT:-./gfs_to_contours.py}"
FILES_DIR="${FILES_DIR:-./files}"

# Clean up files directory
echo "Cleaning files directory: $FILES_DIR"
rm -f "$FILES_DIR"/*

# Execute the Python script
echo "Running Python script: $PYTHON_SCRIPT"
~/pyenv/bin/python3 "$PYTHON_SCRIPT"

if [ $? -eq 0 ]; then
    echo "Python script executed successfully."

    # Copy files to the remote server
    echo "Copying files from $SOURCE_PATH to $DEST_PATH"
    scp "$SOURCE_PATH"/*.geojson "$DEST_PATH"

    if [ $? -eq 0 ]; then
        echo "Files copied successfully."
    else
        echo "Error: Failed to copy files."
        exit 1
    fi
else
    echo "Error: Python script execution failed."
    exit 1
fi

