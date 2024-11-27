import math
from PIL import Image, ImageDraw
import numpy as np
import pygrib
import pandas as pd
import requests
import os

# Constants for Mercator projection
TILE_SIZE = 256  # Each tile is 256x256 pixels

def lat_lon_to_pixels(lat, lon, zoom):
    """
    Converts latitude and longitude to pixel coordinates at a given zoom level.
    """
    siny = math.sin(lat * math.pi / 180.0)
    siny = min(max(siny, -0.9999), 0.9999)
    x = TILE_SIZE * (0.5 + lon / 360.0 * (2 ** zoom))
    y = TILE_SIZE * (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi) * (2 ** zoom))
    return x, y

def generate_tile(data, zoom, x_tile, y_tile):
    """
    Generates a PNG tile for a specific zoom level and tile coordinates.
    """
    # Create a blank image
    image = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)

    # Tile boundaries in Mercator projection
    n = 2 ** zoom
    lon_min = x_tile / n * 360.0 - 180.0
    lon_max = (x_tile + 1) / n * 360.0 - 180.0
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y_tile / n))))
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y_tile + 1) / n))))

    # Draw points from the data
    for _, point in data.iterrows():
        lat, lon, amplitude = point["latitude"], point["longitude"], point["wave_height"]
        if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max:
            # Convert lat/lon to pixel coordinates
            px, py = lat_lon_to_pixels(lat, lon, zoom)
            px = int(px - x_tile * TILE_SIZE)
            py = int(py - y_tile * TILE_SIZE)

            # Draw a circle with size based on amplitude
            size = int(amplitude * 5)  # Scale amplitude to size
            draw.ellipse((px - size, py - size, px + size, py + size), fill=(255, 0, 0, 128))

    return image

def save_tile(image, zoom, x_tile, y_tile, output_dir):
    """
    Saves a tile to the appropriate folder structure.
    """
    path = f"{output_dir}/{zoom}/{x_tile}/"
    os.makedirs(path, exist_ok=True)
    image.save(f"{path}/{y_tile}.png")

# Example data (latitude, longitude, amplitude)
#data = [
#    {"latitude": 34.0522, "longitude": -118.2437, "wave_amplitude": 1.5},
#    {"latitude": 34.1000, "longitude": -118.5000, "wave_amplitude": 0.8},
#    {"latitude": 34.2000, "longitude": -118.6000, "wave_amplitude": 2.0},
#]



df = pd.DataFrame(columns=['datetime', 'latitude', 'longitude', 'wave_height', 'wave_period', 'wave_direction'])
getcols = ['wave_height', 'wave_period', 'wave_direction']
i = 0

def extract_from_grib2(filepath):
    grbs = pygrib.open(filepath)
    wave_height_data = []
    height_param_name = 'Significant height of total swell'  # Adjust based on actual GRIB content
    period_param_name = 'Mean period of total swell'  # Adjust based on actual GRIB content
    direction_param_name = 'Direction of swell waves'  # Adjust based on actual GRIB content

    height_messages = grbs.select(name=height_param_name)
    period_messages = grbs.select(name=period_param_name)
    direction_messages = grbs.select(name=direction_param_name)

    for i in range(len(height_messages)):
        height_msg = height_messages[i]
        period_msg = period_messages[i]  # Assuming matching indices
        direction_msg = direction_messages[i]  # Assuming matching indices

        # Verify that all messages have the same valid date
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

for i in range(1, 2): # forecasting 48 hours ahead
    # format number to 3 digits
    if i < 10:
        i = f"00{i}"
    elif i < 100:
        i = f"0{i}"
    else:
        i = f"{i}"
    # url = f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.20241124/18/wave/gridded/gfswave.t00z.epacif.0p16.f{i}.grib2"
    url = f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.20241124/18/wave/gridded/gfswave.t18z.wcoast.0p16.f056.grib2"

    response = requests.get(url)
    response.raise_for_status()  # This will raise an exception if there was an error downloading the file

    print(f"File {i} downloaded successfully")
    file_path = f"gfswave.t00z.epacif.9km.f{i}.grib2"

    with open(file_path, "wb") as file:
        file.write(response.content)

    d = pd.DataFrame(extract_from_grib2(file_path))
    print(d)

    # render and save tiles
    zoom = 12
    output_dir = "./tiles"
    for x_tile in range(0, 2 ** zoom):  # Adjust ranges for zoom level and data coverage
        for y_tile in range(0, 2 ** zoom):
            tile_image = generate_tile(d, zoom, x_tile, y_tile)
            save_tile(tile_image, zoom, x_tile, y_tile, output_dir)

    # df = pd.concat([df, d], ignore_index=True)



