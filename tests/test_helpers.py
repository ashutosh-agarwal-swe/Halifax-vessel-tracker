import numpy as np
import pandas as pd

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


def test_formula_text_is_escaped():
    for text in ["=1+1", "+1", "-1", "@SUM(A1)", "\tX", "\rX"]:
        assert helpers.escape_formula_text(text) == "'" + text


def test_plain_text_and_numbers_are_not_escaped():
    assert helpers.escape_formula_text("DARK STAR") == "DARK STAR"
    assert helpers.escape_formula_text(-66.5) == -66.5


def test_spreadsheet_safe_only_touches_text_columns():
    df = pd.DataFrame({"vessel_name": ["=1+1", "DARK STAR", None],
                       "lon": [-66.1, -66.2, -66.3]})
    safe = helpers.spreadsheet_safe(df)
    assert list(safe["vessel_name"][:2]) == ["'=1+1", "DARK STAR"]
    assert pd.isna(safe["vessel_name"][2])
    assert list(safe["lon"]) == [-66.1, -66.2, -66.3]
    assert df["vessel_name"][0] == "=1+1"
