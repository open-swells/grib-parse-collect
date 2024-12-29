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


def extract_from_grib2(filepath):
    grbs = pygrib.open(filepath)
    wave_height_data = []
    height_param_name = 'Significant height of total swell'
    period_param_name = 'Mean period of total swell'
    direction_param_name = 'Direction of swell waves'

    height_messages = grbs.select(name=height_param_name)
    period_messages = grbs.select(name=period_param_name)
    direction_messages = grbs.select(name=direction_param_name)

    for i in range(len(height_messages)):
        height_msg = height_messages[i]
        period_msg = period_messages[i]
        direction_msg = direction_messages[i]

        if height_msg.validDate == period_msg.validDate == direction_msg.validDate:
            date = height_msg.validDate
            lats, lons = height_msg.latlons()
            height_data = height_msg.values
            period_data = period_msg.values
            direction_data = direction_msg.values

            for i in range(len(lats)):
                for j in range(len(lats[0])):
                    if np.ma.is_masked(height_data[i][j]):
                        continue
                    wave_height_data.append({
                        'datetime': date,
                        'latitude': lats[i][j],
                        'longitude': lons[i][j],
                        'wave_height': height_data[i][j],
                        'wave_period': period_data[i][j],
                        'wave_direction': direction_data[i][j]
                    })
    return wave_height_data

def save_to_csv(data, csv_path):
    # Write the data to a CSV file
    with open(csv_path, mode='w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    print(f"Data saved to {csv_path}")



def calculate_contours3(csv_path, geojson_path, resolution=(30, 15)):
    """
    Calculate contours with reduced resolution and fewer levels.
    Args:
        csv_path: Path to the input CSV containing columns:
                  longitude, latitude, wave_height.
        geojson_path: Path to the output GeoJSON file with contour polygons.
        resolution: Tuple (# of longitude bins, # of latitude bins).
    """
    # 1. Read CSV data
    lons, lats, heights = [], [], []
    with open(csv_path, mode='r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            lons.append(float(row['longitude']))
            lats.append(float(row['latitude']))
            heights.append(float(row['wave_height']))

    # 2. Prepare grid
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    lon_bins = np.linspace(min_lon, max_lon, resolution[0])
    lat_bins = np.linspace(min_lat, max_lat, resolution[1])
    lon_grid, lat_grid = np.meshgrid(lon_bins, lat_bins)

    # 3. Interpolate data onto grid
    z_grid = griddata(
        (lons, lats), heights,
        (lon_grid, lat_grid),
        method='linear',
        fill_value=np.nan
    )

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
    print(f"Contours saved to {geojson_path}")
    
    plt.close()


def calculate_contours2(csv_path, geojson_path, resolution=(90, 45), num_levels=5):
    """
    Calculate contours with reduced resolution and fewer levels.
    Args:
        resolution: Tuple indicating the number of longitude and latitude bins.
        num_levels: Number of contour levels.
    """
    # Load data from the CSV
    lons, lats, heights = [], [], []
    with open(csv_path, mode='r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            lons.append(float(row['longitude']))
            lats.append(float(row['latitude']))
            heights.append(float(row['wave_height']))

    # Create a coarser grid
    lon_grid = np.linspace(min(lons), max(lons), resolution[0])
    lat_grid = np.linspace(min(lats), max(lats), resolution[1])
    lon_grid, lat_grid = np.meshgrid(lon_grid, lat_grid)

    # Create grids for sum and count
    height_sum = np.zeros((len(lat_grid[:, 0])-1, len(lon_grid[0, :])-1))
    count_grid = np.zeros_like(height_sum)
    
    # Bin the data and calculate averages
    for lon, lat, height in zip(lons, lats, heights):
        lon_idx = np.searchsorted(lon_grid[0, :], lon) - 1
        lat_idx = np.searchsorted(lat_grid[:, 0], lat) - 1
        if 0 <= lon_idx < height_sum.shape[1] and 0 <= lat_idx < height_sum.shape[0]:
            height_sum[lat_idx, lon_idx] += height
            count_grid[lat_idx, lon_idx] += 1
    
    # Avoid divide-by-zero and calculate averages
    count_grid[count_grid == 0] = 1  # Replace zero counts with ones to avoid div-by-zero
    height_grid = height_sum / count_grid

    # Ensure shapes match the grid
    # lon_grid = lon_grid[:-1, :-1]  # Trim edges to match grid output
    # lat_grid = lat_grid[:-1, :-1]

    # Generate contours with specific levels
    contour_levels = [0, 0.2, 0.8, 2.0, 4.0, 6.0]
    contours = plt.contour(lon_grid, lat_grid, height_grid, levels=contour_levels)

    # Convert contours to GeoJSON
    features = []
    for level, segments in zip(contours.levels, contours.allsegs):
        for segment in segments:
            line = LineString(segment)
            features.append(Feature(geometry=line, properties={"level": level}))

    geojson_data = FeatureCollection(features)

    # Save GeoJSON
    with open(geojson_path, 'w') as geojson_file:
        geojson_file.write(dumps(geojson_data))
    print(f"Contours saved to {geojson_path}")


def calculate_contours(csv_path, geojson_path, resolution=(180, 90), num_levels=5):
    """
    Calculate contours with reduced resolution and fewer levels.
    Args:
        resolution: Tuple indicating the number of longitude and latitude bins.
        num_levels: Number of contour levels.
    """
    # Load data from the CSV
    lons, lats, heights = [], [], []
    with open(csv_path, mode='r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            lons.append(float(row['longitude']))
            lats.append(float(row['latitude']))
            heights.append(float(row['wave_height']))

    # Create a coarser grid
    lon_bins = np.linspace(min(lons), max(lons), resolution[0])
    lat_bins = np.linspace(min(lats), max(lats), resolution[1])

    # Aggregate data into the coarse grid
    height_grid = np.zeros((len(lat_bins) - 1, len(lon_bins) - 1))
    counts_grid = np.zeros_like(height_grid)
    for lon, lat, height in zip(lons, lats, heights):
        lon_idx = np.searchsorted(lon_bins, lon) - 1
        lat_idx = np.searchsorted(lat_bins, lat) - 1
        if 0 <= lon_idx < height_grid.shape[1] and 0 <= lat_idx < height_grid.shape[0]:
            height_grid[lat_idx, lon_idx] += height
            counts_grid[lat_idx, lon_idx] += 1

    # Avoid divide-by-zero and calculate averages
    counts_grid[counts_grid == 0] = 1  # Replace zero counts with ones to avoid div-by-zero
    height_grid /= counts_grid

    # Create the coordinate grid
    lon_grid, lat_grid = np.meshgrid(
        (lon_bins[:-1] + lon_bins[1:]) / 2,  # Bin centers
        (lat_bins[:-1] + lat_bins[1:]) / 2
    )

    # Generate contours with fewer levels
    contour_levels = np.linspace(np.nanmin(height_grid), np.nanmax(height_grid), num_levels)
    contours = plt.contour(lon_grid, lat_grid, height_grid, levels=contour_levels)

    # Convert contours to GeoJSON
    features = []
    for level, segments in zip(contours.levels, contours.allsegs):
        for segment in segments:
            line = LineString(segment)
            features.append(Feature(geometry=line, properties={"level": level}))

    geojson_data = FeatureCollection(features)

    # Save GeoJSON
    with open(geojson_path, 'w') as geojson_file:
        geojson_file.write(dumps(geojson_data))
    print(f"Contours saved to {geojson_path}")


# Main processing
for i in range(0, 24):
    file_index = f"{i:03}"  # Format index with leading zeros
    file_path = f"gfswave.t00z.global.9km.f{file_index}.grib2"
    csv_path = f"wave_data_{file_index}.csv"
    geojson_path = f"contours_{file_index}.geojson"
    shp_file_path = f"./land/ne_10m_land.shp"

    if not os.path.exists(file_path):
        url = f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.20241220/18/wave/gridded/gfswave.t18z.global.0p16.f{file_index}.grib2"
        response = requests.get(url)
        response.raise_for_status()

        with open(file_path, "wb") as file:
            file.write(response.content)
        print(f"File {file_index} downloaded successfully")

    if not os.path.exists(csv_path):
        data = extract_from_grib2(file_path)
        save_to_csv(data, csv_path)

    # Use reduced resolution and fewer levels for contours
    # calculate_contours3(csv_path, geojson_path, resolution=(90, 45), num_levels=5)
    calculate_contours3(csv_path, geojson_path, resolution=(90, 45))
    # calculate_contours4(csv_path, geojson_path, shp_file_path, resolution=(90, 45))

