import numpy as np

import config
from src import helpers


def test_haversine_one_degree_of_latitude():
    # One degree of latitude is about 111 km anywhere on Earth.
    distance = helpers.haversine_km(45.0, -66.0, 46.0, -66.0)
    assert abs(distance - 111.2) < 0.5


def test_haversine_same_point_is_zero():
    assert helpers.haversine_km(45.0, -66.0, 45.0, -66.0) == 0


def test_haversine_works_on_arrays():
    lats = np.array([45.0, 45.0])
    lons = np.array([-66.0, -66.0])
    distances = helpers.haversine_km(lats, lons, lats + 1, lons)
    assert len(distances) == 2


def test_port_centre_is_near_port():
    name, lat, lon, radius = config.PORTS[0]
    assert helpers.is_near_port([lat], [lon])[0]


def test_middle_of_bay_is_not_near_port():
    assert not helpers.is_near_port([44.40], [-63.60])[0]


def test_edge_of_study_area():
    middle_lon = (config.LON_MIN + config.LON_MAX) / 2
    middle_lat = (config.LAT_MIN + config.LAT_MAX) / 2
    assert helpers.is_near_edge([config.LAT_MIN + 0.001], [middle_lon])[0]
    assert not helpers.is_near_edge([middle_lat], [middle_lon])[0]


def test_routine_label():
    assert helpers.routine_label(30) == "fishing"
    assert helpers.routine_label(70) == ""
    assert helpers.routine_label(float("nan")) == ""
