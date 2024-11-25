#!/bin/bash

# Navigate to the directory where you want to delete the files
# cd /path/to/your/directory

# Delete all files ending with .grib2 in the current directory
find . -type f -name '*.grib2' -exec rm {} +

echo "All .grib2 files have been deleted."


