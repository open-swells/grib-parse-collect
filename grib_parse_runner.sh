#!/bin/bash

# Load environment variables from config file
# Define absolute paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source the .env file
if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
else
    echo "Error: .env file not found at $SCRIPT_DIR/.env"
    exit 1
fi

# Verify required environment variables
for var in PYTHON_INTERPRETER PYTHON_SCRIPT FILES_DIR SOURCE_PATH DEST_PATH; do
    if [ -z "${!var}" ]; then
        echo "Error: $var is not set in .env file"
        exit 1
    fi
done

# Clean up files directory
echo "Cleaning files directory: $FILES_DIR"
rm -f "$FILES_DIR"/*

# Execute the Python script
echo "Running Python script: $PYTHON_SCRIPT with interpreter: $PYTHON_INTERPRETER"
"$PYTHON_INTERPRETER" "$PYTHON_SCRIPT"

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

