#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL=false
LOCAL_DEST_PATH="${LOCAL_DEST_PATH:-"$SCRIPT_DIR/../open-swells-app/static"}"

usage() {
    echo "Usage: $0 [--local]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --local)
            LOCAL=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
    shift
done

copy_files_locally() {
    local source_path="${SOURCE_PATH:-"$SCRIPT_DIR/files"}"
    local dest_path="$LOCAL_DEST_PATH"

    if [ ! -d "$source_path" ]; then
        echo "Error: source path not found at $source_path" >&2
        exit 1
    fi

    if [ ! -d "$dest_path" ]; then
        echo "Error: local destination path not found at $dest_path" >&2
        exit 1
    fi

    if ! command -v rsync >/dev/null; then
        echo "Error: rsync is required for local copy" >&2
        exit 1
    fi

    shopt -s nullglob
    local contour_files=("$source_path"/*.geojson "$source_path"/*.geojson.gz "$source_path"/*.png)
    shopt -u nullglob

    if [ ${#contour_files[@]} -eq 0 ]; then
        echo "No contour files to copy from $source_path"
        exit 0
    fi

    echo "Copying ${#contour_files[@]} contour files from $source_path to $dest_path"
    rsync -t --delay-updates "${contour_files[@]}" "$dest_path/"

    if [ -f "$source_path/metadata.json" ]; then
        echo "Copying metadata.json"
        rsync -t "$source_path/metadata.json" "$dest_path/"
    fi
}

mkdir -p "$SCRIPT_DIR/logs"
exec >>"$SCRIPT_DIR/logs/grib-run.log" 2>&1
echo "==== $(date -Is) START $$ ===="

# set -e matters for ordering: if generation fails, the copy step never
# runs, so the server keeps serving the previous complete run.
set -euo pipefail

echo "Deleting local grib files"
"$SCRIPT_DIR/scripts/delete_gribs.sh"

echo "Starting grib parse runner"
"$SCRIPT_DIR/scripts/grib_parse_runner.sh"

if [ "$LOCAL" = true ]; then
    echo "Copying files locally to open-swells-app"
    copy_files_locally
else
    echo "Copying files to server"
    "$SCRIPT_DIR/scripts/grib_copy_to_server.sh"
fi

echo "All scripts executed successfully"
