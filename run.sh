#!/usr/bin/env bash
exec >>./logs/grib-run.log 2>&1
echo "==== $(date -Is) START $$ ===="

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Deleting local grib files"
"$SCRIPT_DIR/scripts/delete_gribs.sh"

echo "Starting grib parse runner"
"$SCRIPT_DIR/scripts/grib_parse_runner.sh"

echo "Copying files to server"
"$SCRIPT_DIR/scripts/grib_copy_to_server.sh"


echo "All scripts executed successfully"
