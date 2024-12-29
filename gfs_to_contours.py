import os
import numpy as np
import pygrib
import requests
import csv
from scipy.ndimage import gaussian_filter
import matplotlib.pyplot as plt
from geojson import Feature, FeatureCollection, dumps
from shapely.geometry import Point, Polygon, shape, LineString
import shapefile
from shapely.ops import unary_union
from scipy.interpolate import griddata
import geojson
import datetime as dt
from datetime import datetime, timedelta
import logging
import logging.handlers

# Setup logging
log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Create logger
logger = logging.getLogger('GFSWaveContours')
logger.setLevel(logging.INFO)

# Create handlers
log_file = os.path.join(log_directory, 'gfs_wave_contours.log')
file_handler = logging.handlers.RotatingFileHandler(
    log_file, maxBytes=10485760, backupCount=5)  # 10MB per file, keep 5 backups
console_handler = logging.StreamHandler()

# Create formatters and add it to handlers
log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(log_format)
console_handler.setFormatter(log_format)

# Add handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)


def extract_from_grib2_to_np(filepath):
    grbs = pygrib.open(filepath)
    height_param_name = 'Significant height of total swell'
    period_param_name = 'Mean period of total swell'
    direction_param_name = 'Direction of swell waves'

    height_messages = grbs.select(name=height_param_name)
    period_messages = grbs.select(name=period_param_name)
    direction_messages = grbs.select(name=direction_param_name)

    # We'll only process the first message (timestamp) for now
    height_msg = height_messages[0]
    period_msg = period_messages[0]
    direction_msg = direction_messages[0]

    if height_msg.validDate == period_msg.validDate == direction_msg.validDate:
        date = height_msg.validDate
        lats, lons = height_msg.latlons()
        height_data = height_msg.values
        period_data = period_msg.values
        direction_data = direction_msg.values

        # Create mask for valid (non-masked) data points
        valid_mask = np.logical_not(np.ma.getmask(height_data))
        
        # Get the number of valid points
        n_valid = np.sum(valid_mask)
        
        # Create output arrays
        out_lats = lats[valid_mask]
        out_lons = lons[valid_mask]
        out_heights = height_data[valid_mask]
        out_periods = period_data[valid_mask]
        out_directions = direction_data[valid_mask]
        
        # Stack all arrays horizontally
        return np.column_stack((out_lons, out_lats, out_heights, out_periods, out_directions))
    
    return np.array([])  # Return empty array if no valid data



def calculate_contours4(data, geojson_path, resolution=(30, 15)):
    """
    Calculate contours with reduced resolution and fewer levels.
    Args:
        csv_path: Path to the input CSV containing columns:
                  longitude, latitude, wave_height.
        geojson_path: Path to the output GeoJSON file with contour polygons.
        resolution: Tuple (# of longitude bins, # of latitude bins).
    """
    # 1. read data
    lons, lats, heights = [], [], []
    lons = data[:, 0]
    lats = data[:, 1]
    heights = data[:, 2]


    # 2. Prepare grid
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    lon_bins = np.linspace(min_lon, max_lon, resolution[0])
    lat_bins = np.linspace(min_lat, max_lat, resolution[1])
    lon_grid, lat_grid = np.meshgrid(lon_bins, lat_bins)

    # 3. Bin data directly into grid (no interpolation)
    z_grid = np.full(lon_grid.shape, np.nan)  # Initialize with NaN
    height_sum = np.zeros_like(z_grid)
    count_grid = np.zeros_like(z_grid)
    
    # Bin the data points into the grid
    for lon, lat, height in zip(lons, lats, heights):
        lon_idx = np.searchsorted(lon_bins, lon) - 1
        lat_idx = np.searchsorted(lat_bins, lat) - 1
        if 0 <= lon_idx < z_grid.shape[1] and 0 <= lat_idx < z_grid.shape[0]:
            height_sum[lat_idx, lon_idx] += height
            count_grid[lat_idx, lon_idx] += 1
    
    # Calculate averages where we have data
    mask = count_grid > 0
    z_grid[mask] = height_sum[mask] / count_grid[mask]
    # Leave NaN where we have no data (this will be ignored in contouring)

    # 4. Define contour levels and create contours
    # levels = [0, 0.2, 0.8, 2.0, 4.0, 6.0]
    levels = [0, 0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0]

    contour_set = plt.contour(lon_grid, lat_grid, z_grid, levels=levels)

    # 5. Extract polygons and build GeoJSON features
    features = []
    # contour_set.allsegs is a list of segment lists for each contour level
    for level_index, level_value in enumerate(contour_set.levels):
        # Each entry in contour_set.allsegs[level_index] is a list of Nx2 arrays
        for seg_coords in contour_set.allsegs[level_index]:
            if len(seg_coords) < 3:
                continue  # skip invalid polygons
            poly = Polygon(seg_coords)
            if not poly.is_valid:
                poly = poly.buffer(0)  # attempt to fix invalid geometry
            if not poly.is_empty:
                feature = geojson.Feature(
                    geometry=poly.__geo_interface__,
                    properties={"contour_level": float(level_value)}
                )
                features.append(feature)

    # 6. Write out as GeoJSON
    feature_collection = geojson.FeatureCollection(features)
    with open(geojson_path, 'w') as f:
        geojson.dump(feature_collection, f)
    logger.info(f"Contours saved to {geojson_path}")
    
    plt.close()

def find_latest_gfs_time():
    """Find the latest available GFS wave data time."""
    base_url = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"
    hours = ['18', '12', '06', '00']
    
    # Start with tomorrow's date
    current_date = dt.datetime.now(dt.UTC) + timedelta(days=1)
    
    # Try dates going backwards for 2 days
    for days_back in range(3):
        date_str = current_date.strftime('%Y%m%d')
        
        # Try each hour for this date
        for hour in hours:
            test_url = f"{base_url}gfs.{date_str}/{hour}/wave/gridded/"
            try:
                response = requests.head(test_url)
                if response.status_code == 200:
                    return date_str, hour
            except requests.RequestException:
                continue
        
        # Move to previous day
        current_date -= timedelta(days=1)
    
    raise Exception("Could not find valid GFS wave data in the last 2 days")

# Find the latest available GFS time
date_str, hour = find_latest_gfs_time()
logger.info(f"Found latest GFS wave data for date {date_str} hour {hour}Z")

# Process each forecast hour
for i in range(0, 240):
    file_index = f"{i:03}"  # Format index with leading zeros
    file_path = f"files/gfswave.t{hour}z.global.0p16.f{file_index}.grib2"
    geojson_path = f"files/contours_{file_index}.geojson"

    if not os.path.exists(file_path):
        url = f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.{date_str}/{hour}/wave/gridded/gfswave.t{hour}z.global.0p16.f{file_index}.grib2"
        try:
            response = requests.get(url)
            response.raise_for_status()
            with open(file_path, "wb") as file:
                file.write(response.content)
            logger.info(f"File {file_index} downloaded and saved")
        except requests.RequestException as e:
            logger.error(f"Error downloading file {file_index}: {e}")
            continue
    else: 
        logger.info(f"File {file_index} exists")

    try:
        data = extract_from_grib2_to_np(file_path)
        calculate_contours4(data, geojson_path, resolution=(90, 45))
    except Exception as e:
        logger.error(f"Error processing file {file_index}: {e}")
        continue
