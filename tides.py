"""NOAA CO-OPS tide predictions and recent observed water levels."""

import json
import logging
from datetime import UTC, datetime, timedelta

import requests

logger = logging.getLogger("GFSWaveContours")
DATA_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
METADATA_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations"


def _get_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"].get("message", str(payload["error"])))
    return payload


def _data_params(station: str, product: str) -> dict:
    return {
        "application": "openswells",
        "format": "json",
        "station": station,
        "product": product,
        "datum": "MLLW",
        "time_zone": "gmt",
        "units": "metric",
    }


def fetch_station(
    session: requests.Session,
    station: str,
    *,
    now: datetime | None = None,
    forecast_hours: int = 384,
) -> dict:
    """Fetch hourly tide predictions and the last 48 hours of observations."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    prediction_end = now + timedelta(hours=forecast_hours)

    prediction_params = _data_params(station, "predictions")
    prediction_params.update(
        {
            "begin_date": now.strftime("%Y%m%d"),
            "end_date": prediction_end.strftime("%Y%m%d"),
            "interval": "h",
        }
    )
    predictions = _get_json(session, DATA_URL, prediction_params)

    observation_params = _data_params(station, "water_level")
    observation_params.update(
        {
            "begin_date": (now - timedelta(hours=48)).strftime("%Y%m%d %H:%M"),
            "end_date": now.strftime("%Y%m%d %H:%M"),
        }
    )
    try:
        observations = _get_json(session, DATA_URL, observation_params).get("data", [])
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        # Prediction-only subordinate stations legitimately have no gauge.
        logger.warning("No observed water level for station %s: %s", station, exc)
        observations = []

    metadata = _get_json(session, f"{METADATA_URL}/{station}.json")
    station_data = metadata.get("stations", [{}])[0]
    return {
        "id": station,
        "name": station_data.get("name"),
        "lat": station_data.get("lat"),
        "lon": station_data.get("lng"),
        "datum": "MLLW",
        "units": "meters",
        "time_zone": "UTC",
        "predictions": predictions.get("predictions", []),
        "observations": observations,
    }


def write_tides(
    session: requests.Session,
    station_ids: list[str],
    output_path: str,
    *,
    now: datetime | None = None,
) -> tuple[int, int]:
    """Write one resilient tide payload for all configured CO-OPS stations."""
    stations = []
    errors = []
    for station_id in station_ids:
        try:
            stations.append(fetch_station(session, station_id, now=now))
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            logger.error("Tide station %s failed: %s", station_id, exc)
            errors.append({"station": station_id, "error": str(exc)})

    payload = {
        "generated_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "source": "NOAA CO-OPS",
        "stations": stations,
        "errors": errors,
    }
    with open(output_path, "w") as output:
        json.dump(payload, output, separators=(",", ":"))
    logger.info("Tides saved to %s (%d stations, %d errors)", output_path, len(stations), len(errors))
    return len(stations), len(errors)
