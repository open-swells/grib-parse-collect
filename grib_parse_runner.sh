#!/bin/bash

# Path to the Python script
PYTHON_SCRIPT="${PYTHON_SCRIPT:-/home/evan/grib-parse-collect/gfs_to_contours.py}"

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

