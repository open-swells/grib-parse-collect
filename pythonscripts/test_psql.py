import numpy as np
import pygrib
import requests
import psycopg2

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


# PostgreSQL connection setup
conn = psycopg2.connect(
    dbname="wave_forecast",
    user="postgres",          # Replace with your username
    password="psql_pw",  # Replace with your password
    host="localhost",
    port="5432"
)
cursor = conn.cursor()

# Forecasting for 48 hours ahead
for i in range(1, 24):
    if i < 10:
        i = f"00{i}"
    elif i < 100:
        i = f"0{i}"
    else:
        i = f"{i}"

    url = f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.20241219/18/wave/gridded/gfswave.t18z.wcoast.0p16.f{i}.grib2"

    response = requests.get(url)
    response.raise_for_status()

    print(f"File {i} downloaded successfully")
    file_path = f"gfswave.t00z.epacif.9km.f{i}.grib2"

    with open(file_path, "wb") as file:
        file.write(response.content)

    data = extract_from_grib2(file_path)

    for entry in data:
        cursor.execute("""
            INSERT INTO wave_forecast (datetime, wave_height, wave_period, wave_direction, geom)
            VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326));
        """, (
            entry['datetime'],
            float(entry['wave_height']),
            float(entry['wave_period']),
            float(entry['wave_direction']),
            float(entry['longitude']),
            float(entry['latitude'])
        ))

    conn.commit()
    print(f"Data for file {file_path} inserted into database")

conn.close()

