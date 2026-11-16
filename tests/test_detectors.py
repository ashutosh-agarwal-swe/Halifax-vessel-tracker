"""Small hand-made examples for the loitering and rendezvous detectors."""

import pandas as pd

from src import detect_loitering, detect_rendezvous


def make_track(mmsi, name, vessel_type, start, minutes, lat, lon, sog):
    return pd.DataFrame({
        "mmsi": mmsi,
        "timestamp": pd.date_range(start, periods=minutes, freq="min", tz="UTC"),
        "lat": lat,
        "lon": lon,
        "sog": sog,
        "cog": 0.0,
        "vessel_name": name,
        "vessel_type": vessel_type,
        "length_m": 100,
    })


def test_slow_ship_at_sea_is_loitering():
    df = make_track(316000001, "SLOW", 70, "2026-01-05 00:00", 180, 44.40, -63.60, 0.5)
    result = detect_loitering.find_loitering(df)
    assert len(result) == 1
    assert not result["likely_routine"].iloc[0]


def test_short_stop_is_not_loitering():
    df = make_track(316000001, "BRIEF", 70, "2026-01-05 00:00", 60, 44.40, -63.60, 0.5)
    assert len(detect_loitering.find_loitering(df)) == 0


def test_fast_ship_is_not_loitering():
    df = make_track(316000001, "FAST", 70, "2026-01-05 00:00", 180, 44.40, -63.60, 12.0)
    assert len(detect_loitering.find_loitering(df)) == 0


def test_slow_ship_in_port_is_not_loitering():
    df = make_track(316000001, "DOCKED", 70, "2026-01-05 00:00", 180, 44.64, -63.57, 0.1)
    assert len(detect_loitering.find_loitering(df)) == 0


def test_fishing_boat_is_marked_routine():
    df = make_track(316000001, "FISHER", 30, "2026-01-05 00:00", 180, 44.40, -63.60, 0.5)
    result = detect_loitering.find_loitering(df)
    assert result["likely_routine"].iloc[0]


def test_two_slow_ships_side_by_side_are_a_rendezvous():
    a = make_track(316000001, "A", 70, "2026-01-05 00:00", 60, 44.350, -63.700, 0.5)
    b = make_track(316000002, "B", 80, "2026-01-05 00:00", 60, 44.351, -63.701, 0.5)
    result = detect_rendezvous.find_rendezvous(pd.concat([a, b]))
    assert len(result) == 1
    assert result["duration_minutes"].iloc[0] >= 55
    assert result["closest_km"].iloc[0] < 0.5


def test_ships_far_apart_are_not_a_rendezvous():
    a = make_track(316000001, "A", 70, "2026-01-05 00:00", 60, 44.35, -63.70, 0.5)
    b = make_track(316000002, "B", 80, "2026-01-05 00:00", 60, 44.40, -63.70, 0.5)
    assert len(detect_rendezvous.find_rendezvous(pd.concat([a, b]))) == 0


def test_close_ships_in_diagonal_grid_cells_are_a_rendezvous():
    a = make_track(316000001, "A", 70, "2026-01-05 00:00", 60, 44.350, -63.700, 0.5)
    detect_rendezvous.add_grid_cells(a)
    # Put B just over the north-east corner of A's cell, about 0.4 km away.
    a_cell = a.iloc[0]
    probe = pd.DataFrame({"lat": [a_cell["lat"]], "lon": [a_cell["lon"]]})
    while True:
        probe["lat"] += 0.0001
        detect_rendezvous.add_grid_cells(probe)
        if probe["lat_cell"].iloc[0] != a_cell["lat_cell"]:
            break
    while True:
        probe["lon"] += 0.0001
        detect_rendezvous.add_grid_cells(probe)
        if probe["lon_cell"].iloc[0] != a_cell["lon_cell"]:
            break
    corner_lat, corner_lon = probe["lat"].iloc[0], probe["lon"].iloc[0]
    a = make_track(316000001, "A", 70, "2026-01-05 00:00", 60, corner_lat - 0.0013, corner_lon - 0.0017, 0.5)
    b = make_track(316000002, "B", 80, "2026-01-05 00:00", 60, corner_lat + 0.0013, corner_lon + 0.0017, 0.5)
    result = detect_rendezvous.find_rendezvous(pd.concat([a, b]))
    assert len(result) == 1


def test_close_ships_either_side_of_180_degrees_are_a_rendezvous():
    a = make_track(316000001, "A", 70, "2026-01-05 00:00", 60, 44.350, 179.998, 0.5)
    b = make_track(316000002, "B", 80, "2026-01-05 00:00", 60, 44.350, -179.998, 0.5)
    assert len(detect_rendezvous.find_rendezvous(pd.concat([a, b]))) == 1


def test_ships_passing_at_speed_are_not_a_rendezvous():
    a = make_track(316000001, "A", 70, "2026-01-05 00:00", 60, 44.350, -63.700, 12.0)
    b = make_track(316000002, "B", 80, "2026-01-05 00:00", 60, 44.351, -63.701, 12.0)
    assert len(detect_rendezvous.find_rendezvous(pd.concat([a, b]))) == 0
