#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

ENV_FILE="${ENV_FILE:-"$PROJECT_ROOT/.env"}"
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: env file not found at $ENV_FILE" >&2
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

SOURCE_PATH="${SOURCE_PATH:-${PROJECT_ROOT}/files}"
DEST_PATH="${DEST_PATH:-}"
SSH_KEY_PATH="${SSH_KEY_PATH:-}"

for var in SOURCE_PATH DEST_PATH SSH_KEY_PATH; do
    value="${!var:-}"
    if [ -z "$value" ]; then
        echo "Error: $var must be set in the environment." >&2
        exit 1
    fi
done

if [ ! -d "$SOURCE_PATH" ]; then
    echo "Error: source path not found at $SOURCE_PATH" >&2
    exit 1
fi

if [ ! -f "$SSH_KEY_PATH" ]; then
    echo "Error: SSH key not found at $SSH_KEY_PATH" >&2
    exit 1
fi

shopt -s nullglob
geojson_files=("$SOURCE_PATH"/*.geojson)
json_files=("$SOURCE_PATH"/*.json)
shopt -u nullglob

if [ ${#geojson_files[@]} -eq 0 ] && [ ${#json_files[@]} -eq 0 ]; then
    echo "No files to copy from $SOURCE_PATH"
    exit 0
fi

copy_files() {
    local label="$1"
    shift
    local files=("$@")
    if [ ${#files[@]} -eq 0 ]; then
        return
    fi
    echo "Copying $label from $SOURCE_PATH to $DEST_PATH"
    scp -i "$SSH_KEY_PATH" "${files[@]}" "$DEST_PATH"
}

copy_files "geojson files" "${geojson_files[@]}"
copy_files "json files" "${json_files[@]}"

