import numpy as np
import pygrib
import pandas as pd
import requests
import sqlite3


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

# SQLite database setup
db_path = "wave_forecast.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create a table to store GRIB data
cursor.execute("""
CREATE TABLE IF NOT EXISTS wave_forecast (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 datetime TEXT,
 latitude REAL,
 longitude REAL,
 wave_height REAL,
 wave_period REAL,
 wave_direction REAL
)
""")
conn.commit()

# SQLite database setup with SpatiaLite
# db_path = "../open-swells-db/map.db"
# conn = sqlite3.connect(db_path)
# conn.enable_load_extension(True)



for i in range(1, 2): # forecasting 48 hours ahead
    # format number to 3 digits
    if i < 10:
        i = f"00{i}"
    elif i < 100:
        i = f"0{i}"
    else:
        i = f"{i}"
    # url = f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.20241124/18/wave/gridded/gfswave.t00z.epacif.0p16.f{i}.grib2"
    url = f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.20241124/18/wave/gridded/gfswave.t18z.global.0p16.f{i}.grib2"

    response = requests.get(url)
    response.raise_for_status()  # This will raise an exception if there was an error downloading the file

    print(f"File {i} downloaded successfully")
    file_path = f"gfswave.t00z.epacif.9km.f{i}.grib2"

    with open(file_path, "wb") as file:
        file.write(response.content)

    d = pd.DataFrame(extract_from_grib2(file_path))
    d.to_sql("wave_forecast", conn, if_exists="append", index=False)

   #  data = extract_from_grib2(file_path)

   #  for entry in data:
   #      conn.execute("""
   #      INSERT INTO wave_forecast (datetime, wave_height, wave_period, wave_direction, geom)
   #      VALUES (?, ?, ?, ?, MakePoint(?, ?, 4326));
   #      """, (entry['datetime'], entry['wave_height'], entry['wave_period'], entry['wave_direction'],
   #            entry['longitude'], entry['latitude']))
   #  conn.commit()

    print(f"Data for file {file_path} inserted into database")

    # df = pd.concat([df, d], ignore_index=True)
