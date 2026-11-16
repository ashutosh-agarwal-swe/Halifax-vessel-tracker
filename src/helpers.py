"""
Small helper functions that several scripts share.
"""

import numpy as np
import pandas as pd

import config

EARTH_RADIUS_KM = 6371.0
KM_PER_NAUTICAL_MILE = 1.852


def haversine_km(lat1, lon1, lat2, lon2):
    """
    Distance in km between two points on the Earth.

    Works on single numbers and on whole pandas columns / numpy arrays.
    """
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def km_to_nearest_port(lat, lon):
    """
    For every position, how far (in km) is it from the edge of the
    nearest port circle in config.PORTS?

    A value of 0 or less means the position is inside a port circle.
    """
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)

    best = np.full(lat.shape, np.inf)
    for name, port_lat, port_lon, radius_km in config.PORTS:
        distance = haversine_km(lat, lon, port_lat, port_lon) - radius_km
        best = np.minimum(best, distance)
    return best


def is_near_port(lat, lon):
    """True where the position is inside any port circle."""
    return km_to_nearest_port(lat, lon) <= 0


def is_near_edge(lat, lon):
    """
    True where the position is within EDGE_MARGIN_KM of the border of
    the study area. Ships there are probably just leaving the area.
    """
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)

    # One degree of latitude is about 111 km everywhere.
    # One degree of longitude shrinks as you go north.
    margin_lat = config.EDGE_MARGIN_KM / 111.0
    margin_lon = config.EDGE_MARGIN_KM / (111.0 * np.cos(np.radians(lat)))

    near_south = lat < config.LAT_MIN + margin_lat
    near_north = lat > config.LAT_MAX - margin_lat
    near_west = lon < config.LON_MIN + margin_lon
    near_east = lon > config.LON_MAX - margin_lon
    return near_south | near_north | near_west | near_east


def to_epoch_seconds(timestamps):
    """
    Turn a column of timestamps into whole seconds since 1970-01-01 UTC.

    Plain integers are easier to put into bins than timestamps are.
    """
    start = pd.Timestamp("1970-01-01", tz="UTC")
    seconds = (timestamps - start).dt.total_seconds()
    return seconds.astype("int64")


def cell_index(lat, lon):
    """
    Which grid cell is each position in?

    Returns two integer arrays (row, column). Integers are used instead
    of decimals so that two positions in the same cell always get
    exactly the same key.
    """
    size = config.GRID_SIZE_DEG
    cell_y = np.floor(np.asarray(lat, dtype=float) / size).astype("int64")
    cell_x = np.floor(np.asarray(lon, dtype=float) / size).astype("int64")
    return cell_y, cell_x


def routine_label(vessel_type):
    """
    Return a label like "tug" if the ship type normally loiters or meets
    other ships as part of its work, otherwise an empty string.
    """
    if pd.isna(vessel_type):
        return ""
    return config.ROUTINE_TYPES.get(int(vessel_type), "")
