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

PYTHON_SCRIPT="${PYTHON_SCRIPT:-"$PROJECT_ROOT/gfs_to_contours.py"}"
FILES_DIR="${FILES_DIR:-"$PROJECT_ROOT/files"}"
LOG_DIR="${LOG_DIR:-"$PROJECT_ROOT/logs"}"

for var in PYTHON_SCRIPT FILES_DIR LOG_DIR; do
    value="${!var:-}"
    if [ -z "$value" ]; then
        echo "Error: $var must be set in the environment." >&2
        exit 1
    fi
done

if [ ! -f "$PYTHON_SCRIPT" ]; then
    alt_path="$PROJECT_ROOT/$PYTHON_SCRIPT"
    if [ -f "$alt_path" ]; then
        PYTHON_SCRIPT="$alt_path"
    else
        echo "Error: Python script not found at $PYTHON_SCRIPT" >&2
        exit 1
    fi
fi

mkdir -p "$FILES_DIR" "$LOG_DIR"

echo "Cleaning files directory: $FILES_DIR"
rm -f "$FILES_DIR"/*

UV_CANDIDATES=(
    "${UV_BIN:-}"
    "$PROJECT_ROOT/uv"
    "$PROJECT_ROOT/.venv/bin/uv"
)
FOUND_UV=""
for candidate in "${UV_CANDIDATES[@]}"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        FOUND_UV="$candidate"
        break
    fi
done

if [ -z "$FOUND_UV" ]; then
    if command -v uv >/dev/null 2>&1; then
        FOUND_UV="$(command -v uv)"
    else
        echo "Error: unable to locate uv executable. Set UV_BIN or install uv." >&2
        exit 1
    fi
fi

export FILES_DIR LOG_DIR

echo "Running Python script via uv: $PYTHON_SCRIPT"
"$FOUND_UV" run --project "$PROJECT_ROOT" python "$PYTHON_SCRIPT"
