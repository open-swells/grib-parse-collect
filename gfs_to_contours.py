import gzip
import os
import json
import logging
import logging.handlers
import sys
from datetime import datetime, timedelta
import datetime as dt

import numpy as np
import pygrib
import requests
import geojson

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path

from geojson import Feature, FeatureCollection
from shapely.geometry import Polygon
from shapely.ops import transform as shapely_transform
from scipy.ndimage import gaussian_filter

logger = logging.getLogger("GFSWaveContours")
logger.setLevel(logging.INFO)

_GRID_CACHE: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}


def setup_logging(log_directory: str) -> None:
    if logger.handlers:
        return
    os.makedirs(log_directory, exist_ok=True)
    log_file = os.path.join(log_directory, "gfs_wave_contours.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10_485_760, backupCount=5
    )
    console_handler = logging.StreamHandler()
    log_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(log_format)
    console_handler.setFormatter(log_format)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False


def _grid_cache_key(msg) -> tuple:
    keys = []
    for attr in (
        "gridType",
        "Ni",
        "Nj",
        "latitudeOfFirstGridPointInDegrees",
        "longitudeOfFirstGridPointInDegrees",
        "latitudeOfLastGridPointInDegrees",
        "longitudeOfLastGridPointInDegrees",
    ):
        try:
            value = msg[attr]
        except (KeyError, AttributeError, TypeError):
            value = getattr(msg, attr, None)
        if isinstance(value, (int, float)):
            keys.append(float(value))
        else:
            keys.append(value)
    return tuple(keys)


def _get_lat_lon_grid(msg) -> tuple[np.ndarray, np.ndarray]:
    key = _grid_cache_key(msg)
    cached = _GRID_CACHE.get(key)
    if cached is not None:
        return cached
    lats, lons = msg.latlons()
    grid = (np.array(lons, dtype=np.float32), np.array(lats, dtype=np.float32))
    _GRID_CACHE[key] = grid
    return grid


def _gaussian_filter_nan(array: np.ndarray, sigma: float) -> np.ndarray:
    if not sigma or sigma <= 0:
        return array
    if np.isnan(array).all():
        return array
    nan_mask = np.isnan(array)
    filled = np.where(nan_mask, 0.0, array)
    filtered = gaussian_filter(filled, sigma=sigma, mode="nearest")
    weights = gaussian_filter((~nan_mask).astype(np.float32), sigma=sigma, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        filtered = np.divide(
            filtered,
            weights,
            out=np.full_like(filtered, np.nan),
            where=weights > 0,
        )
    filtered[np.logical_and(nan_mask, weights == 0)] = np.nan
    return filtered


def _derive_levels(values: np.ndarray, base_step: float = 0.5, max_levels: int = 60) -> np.ndarray:
    valid = values[np.isfinite(values)]
    if valid.size == 0:
        raise ValueError("No valid data available for contouring.")
    vmax = float(valid.max())
    if vmax <= 0:
        return np.array([0.0, base_step], dtype=float)
    levels = np.arange(0.0, vmax + base_step, base_step, dtype=float)
    if levels.size > max_levels:
        levels = np.linspace(0.0, vmax, max_levels, dtype=float)
    if levels[-1] < vmax:
        levels = np.append(levels, vmax)
    if levels.size < 2:
        levels = np.array([0.0, vmax], dtype=float)
    return levels


def extract_from_grib2_to_np(filepath: str) -> dict:
    grbs = pygrib.open(filepath)
    try:
        height_param_name = "Significant height of total swell"
        period_param_name = "Mean period of total swell"
        direction_param_name = "Direction of swell waves"

        try:
            height_msg = grbs.select(name=height_param_name)[0]
            period_msg = grbs.select(name=period_param_name)[0]
            direction_msg = grbs.select(name=direction_param_name)[0]
        except (IndexError, ValueError) as exc:
            raise RuntimeError(f"Missing required fields in {filepath}") from exc

        if not (
            height_msg.validDate
            == period_msg.validDate
            == direction_msg.validDate
        ):
            raise ValueError("Mismatched valid times between GRIB fields")

        lon_grid, lat_grid = _get_lat_lon_grid(height_msg)
        height_values = np.ma.filled(height_msg.values, np.nan).astype(np.float32)
        period_values = np.ma.filled(period_msg.values, np.nan).astype(np.float32)
        direction_values = np.ma.filled(direction_msg.values, np.nan).astype(np.float32)
        mask = np.ma.getmaskarray(height_msg.values)

        return {
            "lon": lon_grid,
            "lat": lat_grid,
            "height": height_values,
            "height_mask": mask,
            "period": period_values,
            "direction": direction_values,
            "valid_date": height_msg.validDate,
        }
    finally:
        grbs.close()


def calculate_contours4(
    data: dict,
    geojson_path: str,
    *,
    levels: np.ndarray | None = None,
    smoothing_sigma: float = 1.0,
    simplify_tolerance: float | None = None,
    min_area: float | None = None,
    stride: int = 2,
    extra_properties: dict | None = None,
) -> np.ndarray:
    lon_grid = data["lon"]
    lat_grid = data["lat"]
    height_values = data["height"].astype(np.float32, copy=False)
    mask = data.get("height_mask")

    grid = np.where(mask, np.nan, height_values) if mask is not None else height_values
    grid = _gaussian_filter_nan(grid, smoothing_sigma)

    if stride and stride > 1:
        grid = grid[::stride, ::stride]
        lon_grid = lon_grid[::stride, ::stride]
        lat_grid = lat_grid[::stride, ::stride]

    if levels is None:
        levels = _derive_levels(grid)

    masked_data = np.ma.masked_invalid(grid)
    fig, ax = plt.subplots(figsize=(4, 2.5), dpi=100)
    try:
        contour = ax.contourf(
            lon_grid,
            lat_grid,
            masked_data,
            levels=levels,
            antialiased=True,
        )
    finally:
        plt.close(fig)

    if min_area is None:
        lon_spacing = np.nanmedian(np.abs(np.diff(lon_grid, axis=1)))
        lat_spacing = np.nanmedian(np.abs(np.diff(lat_grid, axis=0)))
        if np.isfinite(lon_spacing) and np.isfinite(lat_spacing):
            min_area = float((lon_spacing * lat_spacing) / 8.0)
        else:
            min_area = 0.0

    features: list[Feature] = []
    extra_properties = extra_properties or {}
    valid_time = data.get("valid_date")
    base_properties = dict(extra_properties)
    if valid_time:
        base_properties.setdefault("valid_time", valid_time.isoformat())

    def _iter_paths():
        collections = getattr(contour, "collections", None)
        if collections is not None:
            for collection, lower, upper in zip(
                collections, contour.levels[:-1], contour.levels[1:]
            ):
                for path in collection.get_paths():
                    yield lower, upper, path.to_polygons()
            return

        allsegs = getattr(contour, "allsegs", None)
        if allsegs is None:
            raise RuntimeError(
                "Matplotlib contour output does not expose polygon collections or segments."
            )
        allkinds = getattr(contour, "allkinds", None)

        for idx, (lower, upper) in enumerate(
            zip(contour.levels[:-1], contour.levels[1:])
        ):
            segs = allsegs[idx]
            if not segs:
                continue
            if allkinds is not None:
                kind_list = allkinds[idx]
            else:
                kind_list = [None] * len(segs)
            for seg_coords, kind in zip(segs, kind_list):
                if seg_coords is None or len(seg_coords) < 3:
                    continue
                try:
                    path = Path(seg_coords, kind) if kind is not None else Path(seg_coords)
                    polygons = path.to_polygons()
                except Exception:
                    polygons = [seg_coords]
                if not polygons:
                    continue
                yield lower, upper, polygons

    for lower, upper, polygon_coords in _iter_paths():
        exterior = polygon_coords[0]
        if exterior.shape[0] < 3:
            continue
        holes = [hole for hole in polygon_coords[1:] if hole.shape[0] >= 3]
        polygon = Polygon(exterior, holes)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty:
            continue
        if min_area and polygon.area < min_area:
            continue
        if simplify_tolerance:
            simplified = polygon.simplify(simplify_tolerance, preserve_topology=True)
            if simplified.is_empty:
                continue
            polygon = simplified
        # ~11m precision; full float precision roughly doubles file size
        polygon = shapely_transform(
            lambda x, y, z=None: (np.round(x, 4), np.round(y, 4)), polygon
        )
        properties = {
            "contour_min": float(lower),
            "contour_max": float(upper),
            "contour_mean": float((lower + upper) / 2.0),
        }
        properties.update(base_properties)
        features.append(
            Feature(geometry=polygon.__geo_interface__, properties=properties)
        )

    if not features:
        logger.warning("No contour polygons generated for %s", geojson_path)
    feature_collection = FeatureCollection(features)
    payload = geojson.dumps(feature_collection)
    with open(geojson_path, "w") as f:
        f.write(payload)
    # Precompressed sibling; the web app serves it when clients accept gzip.
    with gzip.open(geojson_path + ".gz", "wt", encoding="utf-8", compresslevel=6) as f:
        f.write(payload)
    logger.info(
        "Contours saved to %s (%d polygons)", geojson_path, len(features)
    )
    return levels


def find_latest_gfs_time(session: requests.Session | None = None) -> tuple[str, str]:
    hours = ["18", "12", "06", "00"]
    base_url = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"

    own_session = False
    if session is None:
        session = requests.Session()
        own_session = True

    try:
        current_date = dt.datetime.now(dt.UTC) + timedelta(days=1)
        for _ in range(3):
            date_str = current_date.strftime("%Y%m%d")
            for hour in hours:
                # NOAA uploads forecast hours progressively; the run directory
                # appears long before it is complete. Probe the last forecast
                # hour we consume so we never process a half-uploaded run.
                test_url = (
                    f"{base_url}gfs.{date_str}/{hour}/wave/gridded/"
                    f"gfswave.t{hour}z.global.0p16.f384.grib2"
                )
                try:
                    response = session.head(test_url, timeout=10)
                    if response.status_code == 200:
                        return date_str, hour
                except requests.RequestException as exc:
                    logger.debug("HEAD request failed for %s: %s", test_url, exc)
                    continue
            current_date -= timedelta(days=1)
    finally:
        if own_session:
            session.close()

    raise RuntimeError("Could not find valid GFS wave data in the last 2 days")


def write_metadata(
    files_dir: str,
    date_str: str,
    hour: str,
    successes: int | None = None,
    failures: int | None = None,
) -> str:
    metadata_path = os.path.join(files_dir, "metadata.json")
    metadata: dict[str, object] = {
        "date": date_str,
        "hour": hour,
        "timestamp": datetime.now(dt.UTC).isoformat(),
        "forecast_start": f"{date_str}_{hour}Z",
    }
    if successes is not None:
        metadata["hours_processed"] = successes
    if failures is not None:
        metadata["hours_failed"] = failures
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info("Saved metadata to %s", metadata_path)
    return metadata_path


def process_forecast_hours(
    hour_sequence,
    date_str: str,
    run_hour: str,
    files_dir: str,
    *,
    stride: int = 2,
    smoothing_sigma: float = 1.0,
    simplify_tolerance: float | None = None,
    session: requests.Session | None = None,
) -> tuple[int, int]:
    base_url = (
        "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"
        f"gfs.{date_str}/{run_hour}/wave/gridded"
    )

    own_session = False
    if session is None:
        session = requests.Session()
        own_session = True

    successes = 0
    failures = 0
    try:
        for forecast_hour in hour_sequence:
            file_index = f"{int(forecast_hour):03}"
            file_name = f"gfswave.t{run_hour}z.global.0p16.f{file_index}.grib2"
            file_path = os.path.join(files_dir, file_name)
            geojson_path = os.path.join(files_dir, f"contours_{file_index}.geojson")

            if not os.path.exists(file_path):
                url = f"{base_url}/{file_name}"
                if not _download_file(session, url, file_path):
                    logger.error("Giving up on file %s", file_index)
                    failures += 1
                    continue
                logger.info("File %s downloaded and saved", file_index)
            else:
                logger.info("File %s exists", file_index)

            try:
                data = extract_from_grib2_to_np(file_path)
                calculate_contours4(
                    data,
                    geojson_path,
                    stride=stride,
                    smoothing_sigma=smoothing_sigma,
                    simplify_tolerance=simplify_tolerance,
                    extra_properties={"forecast_hour": int(forecast_hour)},
                )
                successes += 1
            except Exception as exc:
                failures += 1
                logger.error(
                    "Error processing file %s: %s", file_index, exc, exc_info=True
                )
    finally:
        if own_session:
            session.close()
    return successes, failures


def _download_file(
    session: requests.Session, url: str, file_path: str, attempts: int = 3
) -> bool:
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(url, timeout=120)
            response.raise_for_status()
            # Write then rename so an interrupted download never leaves a
            # partial .grib2 that a later run would treat as complete.
            tmp_path = file_path + ".part"
            with open(tmp_path, "wb") as file:
                file.write(response.content)
            os.replace(tmp_path, file_path)
            return True
        except requests.RequestException as exc:
            logger.warning(
                "Download attempt %d/%d failed for %s: %s", attempt, attempts, url, exc
            )
    return False


def main() -> None:
    files_dir = os.environ.get("FILES_DIR")
    if not files_dir:
        raise EnvironmentError("FILES_DIR environment variable is not set")
    log_dir = os.environ.get("LOG_DIR")
    if not log_dir:
        raise EnvironmentError("LOG_DIR environment variable is not set")

    setup_logging(log_dir)

    stride = max(int(os.environ.get("CONTOUR_STRIDE", "2") or 1), 1)
    smoothing_sigma = float(os.environ.get("CONTOUR_SMOOTHING_SIGMA", "1.0") or 1.0)
    simplify_env = os.environ.get("CONTOUR_SIMPLIFY_TOLERANCE")
    simplify_tolerance = float(simplify_env) if simplify_env else None

    with requests.Session() as session:
        date_str, hour = find_latest_gfs_time(session=session)
        logger.info(
            "Found latest GFS wave data for date %s hour %sZ", date_str, hour
        )
        successes = 0
        failures = 0
        for hour_sequence in (range(0, 121, 3), range(123, 387, 3)):
            ok, failed = process_forecast_hours(
                hour_sequence,
                date_str,
                hour,
                files_dir,
                stride=stride,
                smoothing_sigma=smoothing_sigma,
                simplify_tolerance=simplify_tolerance,
                session=session,
            )
            successes += ok
            failures += failed

        # Metadata is written last (and copied to the server last) so the
        # frontend never sees a run announced before its contours exist.
        write_metadata(files_dir, date_str, hour, successes=successes, failures=failures)

        total = successes + failures
        logger.info("Run complete: %d/%d forecast hours processed", successes, total)
        if successes == 0:
            logger.error("All forecast hours failed; nothing to publish")
            sys.exit(2)
        if failures > total // 4:
            logger.error(
                "Too many failures (%d of %d); marking run as failed", failures, total
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
